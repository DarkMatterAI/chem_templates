# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/06_assembly.ipynb.

# %% ../nbs/06_assembly.ipynb 3
from __future__ import annotations
from .imports import *
from .utils import *
from .chem import Molecule, to_smile
from .template import Template, TemplateResult
from .fragments import combine_dummies, get_dummy_mol, generate_mapping_permutations,\
match_mapping, fuse_smile_on_atom_mapping
from .building_blocks import Synthon, ReactionUniverse, REACTION_GROUPS

# %% auto 0
__all__ = ['AssemblyPool', 'AssemblyInputs', 'Node', 'FragmentNode', 'FragmentLeafNode', 'SynthonPool', 'make_pairs',
           'make_pairs_chunked', 'add_rxn', 'make_assemblies', 'SynthonNode', 'SynthonLeafNode']

# %% ../nbs/06_assembly.ipynb 4
class AssemblyPool():
    def __init__(self, items: list[Molecule]):
        self.items = items
        
    def __len__(self) -> int:
        return len(self.items)
    
    def __getitem__(self, idx: int) -> Molecule:
        return self.items[idx]
    
    def filter(self, filter_func: Callable, worker_pool: Optional[Pool]=None) -> AssemblyPool:
        if worker_pool:
            bools = worker_pool.map(filter_func, self.items)
            
        else:
            bools = [filter_func(i) for i in self.items]
            
        return AssemblyPool([self.items[i] for i in range(len(self.items)) if bools[i]])
    
    def __repr__(self) -> str:
        return f'AssemblyPool: {len(self.items)} items'

# %% ../nbs/06_assembly.ipynb 6
class AssemblyInputs():
    def __init__(self, 
                 pool_dict: dict[str, AssemblyPool], 
                 assembly_chunksize: int,
                 max_assemblies_per_node: int,
                 worker_pool: Optional[Pool]=None, 
                 log: bool=True):
        
        self.pool_dict = pool_dict
        self.assembly_chunksize = assembly_chunksize
        self.max_assemblies_per_node = max_assemblies_per_node
        
        self.worker_pool = worker_pool
            
        self.log = log
        self.assembly_log = {}

# %% ../nbs/06_assembly.ipynb 7
class Node():
    def __init__(self, 
                 name: str, 
                 template: Optional[Template]=None):
        self.name = name
        self.template = template
        
    def template_screen(self, molecule: Molecule) -> bool:
        if self.template is not None:
            output = self.template(molecule)
        else:
            output = TemplateResult(True, [], [])
        
        molecule.add_data({'template_data' : output, 'template_result' : output.result})
            
        return output.result
    
    def _fuse(self, fusion_input):
        raise NotImplementedError

    def fuse(self, fusion_inputs, worker_pool: Optional[Pool]=None):
        if worker_pool:
            outputs = worker_pool.map(self._fuse, fusion_inputs)
        else:
            outputs = [self._fuse(i) for i in fusion_inputs]
        return AssemblyPool(outputs)

# %% ../nbs/06_assembly.ipynb 8
class FragmentNode(Node):
    def __init__(self, 
                 name: str, 
                 children: list[FragmentNode], 
                 template: Optional[Template]=None):
        super().__init__(name, template)
        self.children = children
        self.build_ids()
        self.build_dummies()
        self.grab_leaf_nodes()
        
    def build_ids(self):
        stack = [self]
        current_id = 1
        while stack:
            current = stack.pop()
            current.id = current_id
            current_id += 1
            
            for child in getattr(current, 'children', []):
                stack.append(child)
                
    def build_dummy(self):
        self.dummy = combine_dummies([child.dummy for child in self.children])
        self.dummy_smile = to_smile(self.dummy)
        patt = re.compile('\[\*(.*?)]')
        self.mapping_idxs = sorted([int(i[1:]) for i in patt.findall(self.dummy_smile)])
                
    def build_dummies(self):
        for child in self.children:
            child.build_dummies()
            
        self.build_dummy()
        
    def grab_leaf_nodes(self):
        self.leaf_nodes = []
        stack = [self]
        while stack:
            current = stack.pop()
            if current.children:
                stack += current.children
            else:
                self.leaf_nodes.append(current)
        
    def map_and_screen(self, molecule: Molecule) -> list[Molecule]:
        smile = molecule.smile
        if smile.count('*') != len(self.mapping_idxs):
            return []
        
        mapped_smiles = deduplicate_list(generate_mapping_permutations(smile, self.mapping_idxs, exact=True))
        molecules = [Molecule(i) for i in mapped_smiles]
        molecules = [i for i in molecules if self.template_screen(i)]
        return molecules
    
    def template_screen(self, molecule: Molecule) -> bool:
        if match_mapping(molecule, self.mapping_idxs):
            return super().template_screen(molecule)
        else:
            return False
    
    def assembly_iterator(self, 
                          child_pools: list[FragmentNode], 
                          chunksize:   int) -> list[Tuple[Molecule]]:
        g = product(*[i.items for i in child_pools])
        for first in g:
            yield list(chain([first], islice(g, chunksize - 1)))
    
    def _fuse(self, fusion_inputs: Tuple[Molecule]) -> Molecule:
        fusion_string = '.'.join([i.smile for i in fusion_inputs])
        fused_smile = fuse_smile_on_atom_mapping(fusion_string)
        fusion_data = {
            'source' : self.name,
            'source_molecules' : fusion_inputs,
            'input_smiles' : fusion_string
        }
        molecule = Molecule(fused_smile, data=fusion_data)
        return molecule
    
    def assemble(self, assembly_inputs: AssemblyInputs) -> AssemblyPool:
        child_pools = [child.assemble(assembly_inputs) for child in self.children]
        print(self.name)
        outputs = []
        assembly_iterator = self.assembly_iterator(child_pools, assembly_inputs.assembly_chunksize)
        
        for fusion_inputs in assembly_iterator:
            fused_pool = self.fuse(fusion_inputs, assembly_inputs.worker_pool)
            fused_pool = fused_pool.filter(self.template_screen, worker_pool=assembly_inputs.worker_pool)
            outputs += fused_pool.items
            
            if len(outputs) > assembly_inputs.max_assemblies_per_node:
                break
                
        fused_pool = AssemblyPool(outputs)
        
        if assembly_inputs.log:
            assembly_inputs.assembly_log[self.name] = {'inputs' : child_pools, 'outputs' : fused_pool}
            
        return fused_pool
    
    def repr_swap(self, input_str: str) -> str:
        input_str = input_str.replace(f'Zr:{self.id}', self.name)
        if hasattr(self, 'children'):
            for child in self.children:
                input_str = child.repr_swap(input_str)
                
        return input_str
        
    def __repr__(self) -> str:
        rep_str = f'{self.name}: {self.repr_swap(self.dummy_smile)}'
        if hasattr(self, 'children'):
            rep_str += '\n'
            for child in self.children:
                rep_str += '\n\t' + '\n\t'.join(child.__repr__().split('\n'))
                
        return rep_str
    
class FragmentLeafNode(FragmentNode):
    def __init__(self, 
                 name: str, 
                 mapping_idxs: list[int], 
                 template: Optional[Template]=None):
        self.mapping_idxs = sorted(mapping_idxs)
        super().__init__(name, [], template)
        
    def build_dummy(self):
        self.dummy = get_dummy_mol(self.name, self.mapping_idxs, id=self.id)
        self.dummy_smile = to_smile(self.dummy)
        
    def assemble(self, assembly_inputs: AssemblyInputs) -> AssemblyPool:
        print(self.name)
        pool = assembly_inputs.pool_dict[self.name]
        pool = pool.filter(self.template_screen, worker_pool=assembly_inputs.worker_pool)
        return pool

# %% ../nbs/06_assembly.ipynb 10
class SynthonPool(AssemblyPool):
    def __init__(self, items: list[Synthon]):
        super().__init__(items)
        self.mark_to_synthon = defaultdict(list)
        
        for synthon in self.items:
            for mark in synthon.marks:
                self.mark_to_synthon[mark].append(synthon)
        
    def get_matching(self, query_synthon: Synthon) -> list[Synthon]:
        matching_synthons = []
        for mark in query_synthon.compatible_marks:
            matching_synthons += self.mark_to_synthon[mark]
        return deduplicate_list(matching_synthons)
    
    def filter(self, filter_func: Callable, worker_pool: Optional[Pool]=None) -> SynthonPool:
        if worker_pool:
            bools = worker_pool.map(filter_func, self.items)
            
        else:
            bools = [filter_func(i) for i in self.items]
            
        return SynthonPool([self.items[i] for i in range(len(self.items)) if bools[i]])

# %% ../nbs/06_assembly.ipynb 11
def make_pairs(pool1: SynthonPool, 
               pool2: SynthonPool):
    for s1 in pool1.items:
        matching = pool2.get_matching(s1)
        for s2 in matching:
            yield (s1, s2)

def make_pairs_chunked(pool1: SynthonPool, 
                       pool2: SynthonPool, 
                       chunksize: int):
    g = make_pairs(pool1, pool2)
    for first in g:
        yield list(chain([first], islice(g, chunksize-1)))

def add_rxn(pair: Tuple[Synthon, Synthon], 
            rxn_universe: ReactionUniverse):
    s1, s2 = pair
    return (s1, s2, rxn_universe.get_matching_reactions(s1, s2))

def make_assemblies(pool1: SynthonPool, 
                    pool2: SynthonPool, 
                    rxn_universe: ReactionUniverse, 
                    chunksize: int, 
                    worker_pool: Optional[Pool]=None):
    
    pair_gen = make_pairs_chunked(pool1, pool2, chunksize)
    func = partial(add_rxn, rxn_universe=rxn_universe)
    
    output_assemblies = []
    for chunk in pair_gen:
        
        if worker_pool:
            chunk = worker_pool.map(func, chunk)
        else:
            chunk = [func(i) for i in chunk]

        for assembly in chunk:
            
            if assembly[-1]:
                output_assemblies.append(assembly)
                
            if len(output_assemblies)>= chunksize:
                yield output_assemblies
                output_assemblies = []
    
    
    yield output_assemblies

# %% ../nbs/06_assembly.ipynb 12
class SynthonNode(Node):
    def __init__(self, 
                 name: str, 
                 incoming_node: SynthonNode, 
                 next_node: SynthonNode, 
                 rxn_universe: ReactionUniverse, 
                 n_func: set[int], 
                 template: Optional[Template]=None):
        super().__init__(name, template)
        self.incoming_node = incoming_node
        self.next_node = next_node
        self.rxn_universe = rxn_universe
        self.n_func = n_func
        self.grab_leaf_nodes()
        
    def grab_leaf_nodes(self):
        self.leaf_nodes = []
        stack = [self]
        while stack:
            current = stack.pop()
            if isinstance(current, SynthonLeafNode):
                self.leaf_nodes.append(current)
            else:
                stack.append(current.next_node)
                stack.append(current.incoming_node)
        
    def template_screen(self, synthon: Synthon) -> bool:
        n_func = synthon.recon_smile.count(':')
        if (n_func in self.n_func) or (not self.n_func):
            return super().template_screen(synthon)
        else:
            return False
        
    def reaction_screen(self, synthon: Synthon) -> bool:
        if self.rxn_universe:
            return bool(self.rxn_universe.get_matching_reactions(synthon))
        else:
            return True
        
    def _fuse(self, fusion_inputs: Tuple[Synthon, Synthon, list[FusionReaction]]) -> list[Synthon]:
        s1, s2, valid_rxns = fusion_inputs
        products = flatten_list([rxn.react(s1, s2) for rxn in valid_rxns])
        
        unique_products = defaultdict(list)
        for product in products:
            unique_products[product.smile].append(product)
            
        outputs = []
        for k,v in unique_products.items():
            product = v[0]
            if len(v)>1:
                product.data['reaction_tags'] = flatten_list([i.data['reaction_tags'] for i in v])
            outputs.append(product)
        return outputs
    
    def fuse(self, 
             fusion_inputs: Tuple[Synthon, Synthon, list[FusionReaction]], 
             worker_pool: Optional[Pool]=None) -> SynthonPool:
        if worker_pool:
            outputs = worker_pool.map(self._fuse, fusion_inputs)
        else:
            outputs = [self._fuse(i) for i in fusion_inputs]
        return SynthonPool(flatten_list(outputs))
    
    def assemble(self, assembly_inputs: AssemblyInputs) -> SynthonPool:
        incoming_pool = self.incoming_node.assemble(assembly_inputs)
        incoming_pool = incoming_pool.filter(self.reaction_screen, assembly_inputs.worker_pool)
        
        next_pool = self.next_node.assemble(assembly_inputs)
        next_pool = next_pool.filter(self.reaction_screen, assembly_inputs.worker_pool)
        
        print(self.name)
        
        outputs = []
        
        assembly_generator = make_assemblies(incoming_pool, next_pool, self.rxn_universe,
                                            assembly_inputs.assembly_chunksize, assembly_inputs.worker_pool)
        
        for assemblies in assembly_generator:
            fused_pool = self.fuse(assemblies, assembly_inputs.worker_pool)
            fused_pool = fused_pool.filter(self.template_screen, worker_pool=assembly_inputs.worker_pool)
            outputs += fused_pool.items
            
            if len(outputs) > assembly_inputs.max_assemblies_per_node:
                break
                
        fused_pool = SynthonPool(outputs)
        
        if assembly_inputs.log:
            assembly_inputs.assembly_log[self.name] = {'inputs' : [incoming_pool, next_pool], 
                                                       'outputs' : fused_pool}
            
        return fused_pool
    
    def __repr__(self) -> str:
        return f'Synthon Product: {self.name}'
    
class SynthonLeafNode(SynthonNode):
    def __init__(self, 
                 name: str, 
                 n_func: set[int], 
                 template: Optional[Template]=None):
        super().__init__(name, None, None, None, n_func, template)
        
    def assemble(self, assembly_inputs: AssemblyInputs) -> SynthonPool:
        print(self.name)
        pool = assembly_inputs.pool_dict[self.name]
        pool = pool.filter(self.template_screen, worker_pool=assembly_inputs.worker_pool)
        return pool
    
    def __repr__(self) -> str:
        return f'Synthon Leaf: {self.name}'
