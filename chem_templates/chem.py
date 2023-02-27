# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/01_chem.ipynb.

# %% auto 0
__all__ = ['to_mol', 'to_smile', 'to_kekule', 'canon_smile', 'remove_stereo', 'remove_stereo_smile', 'Molecule', 'Reaction']

# %% ../nbs/01_chem.ipynb 3
from .imports import *
from .utils import *
import rdkit
from rdkit import Chem

# %% ../nbs/01_chem.ipynb 5
def to_mol(smile: str) -> Union[Chem.Mol, None]:

    mol = Chem.MolFromSmiles(smile)
    if mol is not None:
        try:
            Chem.SanitizeMol(mol)
        except:
            mol = None
        
    return mol

def to_smile(mol: Chem.Mol) -> str:
    smile = Chem.MolToSmiles(mol)
    return smile

def to_kekule(smile: str) -> str:
    return Chem.MolToSmiles(to_mol(smile), kekuleSmiles=True)

def canon_smile(smile: str) -> str:
    try:
        return Chem.CanonSmiles(smile)
    except:
        return ''
    
def remove_stereo(mol: Chem.Mol) -> Chem.Mol:
    Chem.rdmolops.RemoveStereochemistry(mol)
    return mol

def remove_stereo_smile(smile: str) -> str:
    if '@' in smile:
        mol = to_mol(smile)
        mol = remove_stereo(mol)
        smile = to_smile(mol)
    return smile

# %% ../nbs/01_chem.ipynb 7
class Molecule():
    def __init__(self, smile: str, data: Optional[dict]=None):
        self.smile = canon_smile(smile)
        self.mol = to_mol(self.smile)
        self.valid = (self.mol is not None) and (self.smile != '')
        
        self.data = {}
        self.add_data(data)
            
    def add_data(self, data: Optional[dict]=None):
        if data is not None:
            self.data.update(data)

# %% ../nbs/01_chem.ipynb 8
class Reaction():
    def __init__(self, reaction_smarts: str):
        self.reaction_smarts = reaction_smarts
        self.reaction = AllChem.ReactionFromSmarts(self.reaction_smarts)
