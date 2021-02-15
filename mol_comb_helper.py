from rdkit import DataStructs
from rdkit import Chem
from rdkit.Chem import rdFingerprintGenerator
from rdkit.Chem.MolStandardize import rdMolStandardize
from rdkit.Chem import Draw, AllChem
from rdkit.Chem import BRICS
from rdkit.Chem.Draw import SimilarityMaps, IPythonConsole
from rdkit.Chem import rdFingerprintGenerator
from rdkit.Chem import MACCSkeys
from rdkit.Chem import ChemicalFeatures
from rdkit import RDConfig
from rdkit import RDLogger
from rdkit.Chem.Pharm2D.SigFactory import SigFactory
from rdkit.Chem.Pharm2D import Generate
from collections import defaultdict, Counter
import numpy as np
import os

RDLogger.DisableLog('rdApp.info')

fpgen = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=4096)


def getIC50(mol):
    return np.random.uniform(0, 1000)


# Open SMILES file and convert each sequence to rdkit molecule
with open("./data/100k_SMILES.txt") as f:
    raw_text = f.read()

raw_data = raw_text.split("\n")
mol_list = [Chem.MolFromSmiles(x) for x in raw_data[:1000]]
ms = [rdMolStandardize.FragmentParent(x) for x in mol_list]

# Get a count of the BRICS bonds within the molecules
cntr = Counter()
for m in ms:
    bbnds = BRICS.FindBRICSBonds(m)
    for aids, lbls in bbnds:
        cntr[lbls] += 1
freqs = sorted([(y, x) for x, y in cntr.items()], reverse=True)

# Keep the top 10 bonds
bondsToKeep = [y for x, y in freqs[:10]]


# Helper functions
def splitMol(mol, bondsToKeep):
    ''' fragments a molecule on a particular set of BRICS bonds. 
    Partially sanitizes the results 
    '''
    bbnds = BRICS.FindBRICSBonds(mol)
    bndsToTry = []
    lbls = []
    for aids, lbl in bbnds:
        if lbl in bondsToKeep:
            bndsToTry.append(mol.GetBondBetweenAtoms(
                aids[0], aids[1]).GetIdx())
            lbls.append([int(x) for x in lbl])
    if not bndsToTry:
        return []
    res = Chem.FragmentOnSomeBonds(mol, bndsToTry, dummyLabels=lbls)
    # We need at least a partial sanitization for the rest of what we will be doing:
    for entry in res:
        entry.UpdatePropertyCache(False)
        Chem.FastFindRings(entry)
    return res


def getDifferenceFPs(mol, bondsToKeep, fpgen):
    ''' generates the difference fingerprint between the molecule
    and each of its fragmentations based on the BRICS bond types passed in.

    This calculates the sum of the fragment fingerprints by just generating the
    fingerprint of the fragmented molecule, so whole-molecule fingerprints like
    atom pairs will not work here. That's fine since they are unlikely to be useful
    with this approach anyway
    '''
    frags = splitMol(mol, bondsToKeep)
    if not frags:
        return []
    res = []
    # get the fingerprint for the molecule:
    molfp = fpgen.GetCountFingerprint(mol)
    # now loop over each fragmentation
    for frag in frags:
        # generate the fingerprint of the fragmented molecule
        # (equivalent to the sum of the fingerprints of the fragments)
        ffp = fpgen.GetCountFingerprint(frag)
        # and keep the difference
        res.append(molfp-ffp)
    return res


def getSumFP(fragMol, fpgen, delta):
    ''' Constructs the sum fingerprint for a fragmented molecule using
    delta as a constant offset

    note that any elements of the fingerprint that are negative after adding the
    constant offset will be set to zero

    '''
    ffp = fpgen.GetCountFingerprint(fragMol)
    for idx, v in delta.GetNonzeroElements().items():
        tv = ffp[idx] + v
        if tv < 0:
            tv = 0
        ffp[idx] = tv
    return ffp


def getAllFrags(mol):
    ''' Creates a dictionary of all fragments and their type of BRICS bond

    '''
    bonding_dict = {}
    for i in range(9):
        frags = splitMol(mol, bondsToKeep[i-1:i])
        if frags:
            bonding_dict[bondsToKeep[i-1]
                         ] = Chem.MolToSmiles(frags[0]).split(".")
    return (bonding_dict)


def combineFrags(mol1, mol2):
    ''' Recombines fragments based on each of their best IC50 values

    '''
    mol1_dict = getAllFrags(mol1)
    mol2_dict = getAllFrags(mol2)
    mol_list = []

    for key in mol1_dict.keys() & mol2_dict.keys():
        l1, r1 = mol1_dict[key]
        l2, r2 = mol2_dict[key]

        min_l = min(l1, l2, key=lambda mol: getIC50(mol))
        min_r = min(r1, r2, key=lambda mol: getIC50(mol))
        mol_list.append(min_l + "." + min_r)

    return (mol_list)


def getCommonBonds(mol1, mol2):
    mol1_dict = getAllFrags(mol1)
    mol2_dict = getAllFrags(mol2)
    common_bonds = []

    for key in mol1_dict.keys() & mol2_dict.keys():
        common_bonds.append(key)

    return (common_bonds)


def getDeltaFP(bondsToKeep, fpgen):
    ''' Gets the best offset delta based on the type of BRICS bond

    '''
    dfps = []
    for m in ms:
        dfps.extend(getDifferenceFPs(m, bondsToKeep, fpgen))

    delta1 = dfps[0]
    for dfp in dfps[1:]:
        delta1 += dfp
    nfps = len(dfps)
    for k, v in delta1.GetNonzeroElements().items():
        delta1[k] = round(v/nfps)

    return (delta1)


def getFinalFingerprint(fragments, delta, fpgen):
    ''' Recombines fragments into a final fingerprint

    '''
    for i in range(len(fragments)):
        fragments[i] = Chem.MolFromSmiles(fragments[i])

    ffps = [getSumFP(x, fpgen, delta)
            for x in fragments]
    return (ffps)


fragments = combineFrags(ms[35], ms[89])
bonds = getCommonBonds(ms[35], ms[89])
delta = getDeltaFP([bonds[0]], fpgen)
finalfp = getFinalFingerprint([fragments[0]], delta, fpgen)

print(finalfp)
