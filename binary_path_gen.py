import json
from typing import List, Tuple, Union
from enum import Enum

# ABI element class and parsing functions

class ABIElement:
    def __init__(self, name: str, type: str, dimension: int, components: List['ABIElement'] = None):
        
        if dimension >= 0:
            assert type == "array"
            assert len (components) == 1

        self.name = name
        self.type = type
        self.dimension = dimension
        self.components = components or []
    
    def makeRepr(self,level):
        components_str = ""
        if self.components:
            components_str = "".join([comp.makeRepr(level+1) for comp in self.components])
        header = f"{self.name}(type={self.type})"
        if self.dimension >= 0:
            header += f"[{self.dimension}]"
        footer = "dynamic" if self.is_dynamic() else "static"
        return f"{'  '*level}{header} - {footer}\n{components_str}"

    def __repr__(self):
        return self.makeRepr(0)

    def is_array(self) -> bool:
        return self.type == "array"

    def is_struct(self) -> bool:
        return self.type == "tuple" or self.type == "function"

    def is_dynamic(self) -> bool:
        return self.type in ["string", "bytes"] or self.dimension == 0 or any(comp.is_dynamic() for comp in self.components)
    
    def is_static(self) -> bool:
        return not self.is_dynamic()
    
    def encoding_weight(self) -> int:
        if self.is_dynamic():
            return 1
        
        if self.is_array():
            return self.dimension * self.components[0].encoding_weight()

        if self.components:
            return sum(components.encoding_weight() for components in self.components)
        
        return 1

    def structIndex(self, name: str) -> int:
        assert self.is_struct()

        index = 0
        for i in range(len(self.components)):
            if self.components[i].name == name:
                return index
            else:
                index += self.components[i].encoding_weight()
        return -1
    
    def arrayIndex(self, index: int) -> int:
        assert self.is_array()

        if self.dimension == 0:
            raise ValueError(f"Cannot compute static array index for dynamic array {self.name}")
        
        if (index >= self.dimension or index < -self.dimension):
            raise ValueError(f"Index {index} out of bounds for array {self.name}")

        return (index if index >= 0 else self.dimension + index) * self.components[0].encoding_weight()

    def nextInStruct(self, name):
        assert self.is_struct()

        for i in range(len(self.components)):
            if self.components[i].name == name:
                return self.components[i]
                
        return None
    
    def nextInArray(self):
        assert self.is_array()

        return self.components[0]

def parse_component(data: dict) -> ABIElement:
    type = data['type']
    name = data['name'] or ""
    if '[' in type and ']' in type:
        dimension_str = type.split('[')[-1].split(']')[0]
        dimension = int(dimension_str) if dimension_str else 0
        data['type'] = type[:type.rfind('[')]
        data['name'] = "_"
        components = [parse_component(data)]
        return ABIElement(name, "array", dimension, components)
    else:
        dimension = -1
        components = [parse_component(comp) for comp in data.get('components', [])]
        return ABIElement(name, type, dimension, components)

def parse_function(data: List) -> ABIElement:
    name = data['name']
    type = data['type']
    components = [parse_component(comp) for comp in data.get('inputs', [])]
    return ABIElement(name,type,-1,components)

def parse_json(json_data: str) -> List[ABIElement]:
    data = json.loads(json_data)
    functions = [parse_function(func) for func in data]
    return functions

# ABI path classes and builder functions

class PathElementType(Enum):
    TUPLE_ELEMENT = int(0x10)   # move by {value} slots from current slot
    ARRAY_ELEMENT = int(0x11)    # current slot is array length, added to offset if negative. multiple by item_size and move by result slots
    REF_ELEMENT = int(0x12)      # read value of current slot. apply read value as offset from current slot
    LEAF_ELEMENT = int(0x13)       # current slot is a leaf type, specifying the type of path end
    SLICE_ELEMENT = int(0x14)           # specify slicing to apply to final leaf value

class PathLeafType(Enum):
    ARRAY_LEAF = 1      # Final offset is start of array encoding
    TUPLE_LEAF = 2      # Final offset is start of tuple encoding
    STATIC_LEAF = 3     # Final offset contains static encoded value (typ data on 32 bytes)
    DYNAMIC_LEAF = 4    # Final offset contains dynamic encoded value (typ length + data)

class PathElement:
    """
    PathElement class represents an element in a binary path. It can be of different types such as tuple element, array element, leaf element, or slice element.

    BNF style spec:

        path                            = tlv(TAG_BINARY_PATH, binary_path);

        binary_path                     = path_elements * 
                                        & path_leaf
                                        & path_slice ?
                                        ;

        path_elements                   = tuple_element 
                                        | array_element;

    Methods:
        __init__(index: int, type: PathElementType): Initializes a tuple or array element.
        __init__(leaf_type: PathLeafType): Initializes a leaf element.
        __init__(start: int, end: int): Initializes a slice element.
        __repr__(): Returns a string representation of the path element.
        to_string(): Converts the path element to a binary string representation ("(1).[2].(0)").
        to_bytes(): Converts the path element to a byte representation. This is the data being signed by the CAL.
    """
    def __init__(self, type: PathElementType, index: int = None, items: int = None, start: int = None, end: int = None, leaf_type: PathLeafType = None):
        self.type = type
        self.index = index
        self.items_weight = items
        self.start = start
        self.end = end
        self.leaf_type = leaf_type
        
    @classmethod
    def from_tuple(cls, index: int):
        return cls(PathElementType.TUPLE_ELEMENT, index = index)
    
    @classmethod
    def from_array(cls, index: int, items: int):
        return cls(PathElementType.ARRAY_ELEMENT,  index=index, items=items)
    
    @classmethod
    def from_ref(cls):
        return cls(PathElementType.REF_ELEMENT)
    
    @classmethod
    def from_leaf(cls, leaf_type: int):
        return cls(PathElementType.LEAF_ELEMENT, leaf_type=PathLeafType(leaf_type))

    @classmethod
    def from_slice(cls, start: int, end: int):
        return cls(PathElementType.SLICE_ELEMENT, start=start, end=end)


    def __repr__(self):
        if self.type == PathElementType.TUPLE_ELEMENT:
            return f"TupleElement(index={self.index})"
        elif self.type == PathElementType.ARRAY_ELEMENT:
            return f"ArrayElement(index={self.index}, items={self.items_weight})"
        elif self.type == PathElementType.REF_ELEMENT:
            return f"RefElement()"
        elif self.type == PathElementType.LEAF_ELEMENT:
            return f"LeafElement(leaf_type={self.leaf_type})"
        elif self.type == PathElementType.SLICE_ELEMENT:
            return f"SliceElement(start={self.start}, end={self.end})"
        else:
            return ""
        
    def to_string(self):
        if self.type == PathElementType.TUPLE_ELEMENT:
            return f"({self.index})"
        elif self.type == PathElementType.ARRAY_ELEMENT:
            return f"[{self.index}]"
        elif self.type == PathElementType.REF_ELEMENT:
            return f"."
        elif self.type == PathElementType.LEAF_ELEMENT:
            if self.leaf_type == PathLeafType.ARRAY_LEAF:
                return "a"
            elif self.leaf_type == PathLeafType.TUPLE_LEAF:
                return "t"
            elif self.leaf_type == PathLeafType.STATIC_LEAF:
                return "s"
            elif self.leaf_type == PathLeafType.DYNAMIC_LEAF:
                return "d"
        elif self.type == PathElementType.SLICE_ELEMENT:
            return f"{{{self.start}:{self.end}}}"
        else:
            return ""
    
    def to_bytes(self):
        tag = self.type.value
        if self.type == PathElementType.TUPLE_ELEMENT:
            length = 2
            value = f"{self.index:04x}"
        elif self.type == PathElementType.ARRAY_ELEMENT:
            length = 4
            index = self.index & 0xFFFF  # Ensure two's complement for negative values
            value = f"{index:04x}{self.items_weight:04x}"
        elif self.type == PathElementType.REF_ELEMENT:
            length = 0
            value = ""
        elif self.type == PathElementType.LEAF_ELEMENT:
            length = 1
            value = f"{self.leaf_type.value:02x}"
        elif self.type == PathElementType.SLICE_ELEMENT:
            length=4
            value = f"{self.start:04x}{self.end:04x}"
        
        ESC = chr(27)
        BOLD = ESC + "[31;1m"
        ITALIC = ESC + "[3m"
        NORMAL = ESC + "[0m"
        tag_str = BOLD + f"{tag:02x}" + NORMAL
        length_str = ITALIC + f"{length:02x}" + NORMAL

        return f"{tag_str} {length_str} {value} " if value else f"{tag_str} {length_str} "

class Path:
    """
    Represents a path in the calldata.

    Attributes:
        path (List[PathElement]): A list of PathElement objects that make up the path.

    Methods:
        __init__(path: List[PathElement]):
            Initializes the Path object with a list of PathElement objects.
            Raises:
                ValueError: If the first element is not a tuple element.
                ValueError: If the last element is not a leaf element or the second to last element is not a leaf element when a slice is present.
                ValueError: If any middle element is not a tuple or array element.
        __repr__():
            Returns a string representation of the Path object.
        to_string():
            Converts the path to a string representation, joining elements with a dot.
        to_bytes():
            Converts the path to a byte representation, joining elements as TLVs.
    """

    def __init__(self, path: List['PathElement']):
        assert len(path) >= 2
        if path[0].type != PathElementType.TUPLE_ELEMENT:
            raise ValueError("First element of path must be a tuple element")
        
        if path[-1].type == PathElementType.SLICE_ELEMENT:
            if len(path) == 2 or path[-2].type != PathElementType.LEAF_ELEMENT:
                raise ValueError("Second to last element of path must be a leaf element when a slice is present")
            tocheck = path[1:-3]
        elif path[-1].type != PathElementType.LEAF_ELEMENT:
            raise ValueError("Last element of path must be a leaf element, when no slice is present")    
        else:
            tocheck = path[1:-2]

        for element in tocheck:
            if element.type != PathElementType.ARRAY_ELEMENT and element.type != PathElementType.TUPLE_ELEMENT and element.type != PathElementType.REF_ELEMENT:
                raise ValueError("Middle of the path must be TUPLE, ARRAY or REF elements")

        self.path = path

    def __repr__(self):
        return f"Path(path={self.path})"

    def to_string(self):
        return "".join([element.to_string() for element in self.path])

    def to_bytes(self):
        return "".join([element.to_bytes() for element in self.path])

# Path building functions
def build_path(path: str, root_function: ABIElement) -> Path:

    elements = path.split('.')

    # pop the slice selector
    slice = elements.pop() if elements[-1] == "[]" or ':' in elements[-1] else None

    path_elements = []   
    
    if len(elements) == 0:
        raise ValueError("Path must have at least one element beyond the slice selector")

    next_abi_element = root_function
    
    # While the current element is dynamic, emit TUPLE_ELEMENT and ARRAY_ELEMENT path elements
    # Otherwise accumlate offsets to get to the final static element
    is_static = next_abi_element.is_static()
    static_offset = 0

    for index,element in enumerate(elements): 
        
        current_abi_element = next_abi_element
        if is_static and current_abi_element.is_dynamic():
            raise ValueError(f"Path element {index}:{element} - Unexpected dynamic element")
        
        if not element.startswith('['):
            # Structure selector
            if not current_abi_element.is_struct():
                raise ValueError(f"Path element {index}:{element} - Unexpected structure selector")

            next_abi_element = current_abi_element.nextInStruct(element)

            if not next_abi_element:
                raise ValueError(f"Path element {index}:{element} - Structure not found in ABI")
        
            if is_static:
                static_offset += current_abi_element.structIndex(element)
            else:
                path_elements.append(PathElement.from_tuple(current_abi_element.structIndex(element)))
        else:
            # Array selector
            if not current_abi_element.is_array():
                raise ValueError(f"Path element {index}:{element} - Unexpected array selector")
            
            next_abi_element = current_abi_element.nextInArray()

            if is_static:
                static_offset += current_abi_element.arrayIndex(int(element[1:-1]))
            else:
                array_index = int(element[1:-1])
                if current_abi_element.dimension == 0:
                    path_elements.append(PathElement.from_array(array_index, next_abi_element.encoding_weight()))
                else:
                    if array_index < 0:
                        array_index += current_abi_element.dimension
                    path_elements.append(PathElement.from_tuple(array_index * next_abi_element.encoding_weight()))

        if next_abi_element.is_dynamic():
            path_elements.append(PathElement.from_ref())

    # Emit a last static offset to a static value
    if is_static:
        path_elements.append(PathElement.from_tuple(static_offset))

    # Emit correct leaf type

    if next_abi_element.is_array():
        path_elements.append(PathElement.from_leaf(PathLeafType.ARRAY_LEAF))
    elif next_abi_element.is_struct():
        path_elements.append(PathElement.from_leaf(PathLeafType.TUPLE_LEAF))
    elif next_abi_element.is_dynamic():
        path_elements.append(PathElement.from_leaf(PathLeafType.DYNAMIC_LEAF))
    elif next_abi_element.is_static():
        path_elements.append(PathElement.from_leaf(PathLeafType.STATIC_LEAF))

    # If slice is present, emit a slice element 
    if slice:
        # Slices should only apply to arrays or dynamic, non struct values
        valid = next_abi_element.is_array() or (next_abi_element.is_dynamic() and not next_abi_element.is_struct())
        if not valid:
            raise ValueError(f"Path element {index}:{element} - Unexpected slice selector")

        if not slice == "[]":
            start, end = slice[1:-1].split(':')
            path_elements.append(PathElement.from_slice(int(start), int(end)))

    return Path(path_elements)

def apply_path(binary_path: Path, input_data: bytes) -> bytes:
    offset = 0
    ref_offset = 0

    path = binary_path.path
    slice = path.pop() if path[-1].type == PathElementType.SLICE_ELEMENT else None

    for element in path:
        if element.type == PathElementType.TUPLE_ELEMENT:
            ref_offset = offset
            offset += element.index * 32
            # print(f"TupleElement: ref_offset={ref_offset / 32} offset={offset / 32}")
        elif element.type == PathElementType.ARRAY_ELEMENT:
            ref_offset = offset
            array_length = int.from_bytes(input_data[offset:offset + 32], byteorder='big')
            if element.index >= array_length:
                raise IndexError(f"Array index {element.index} out of bounds")
            if element.index < 0:
                offset += 32 + (array_length + element.index) * element.items_weight * 32
            else:
                offset += 32 + element.index * element.items_weight * 32
            # print(f"ArrayElement: array_length={array_length} ref_offset={ref_offset / 32} offset={offset / 32}")
        elif element.type == PathElementType.REF_ELEMENT:
            offset = ref_offset + int.from_bytes(input_data[offset:offset + 32], byteorder='big')
            # print(f"RefElement: ref_offset={ref_offset} offset={offset}")
        elif element.type == PathElementType.LEAF_ELEMENT:
            # print(f"LeafElement: offset={offset}")
            if element.leaf_type == PathLeafType.STATIC_LEAF:
                return input_data[offset:offset + 32]
            elif element.leaf_type == PathLeafType.DYNAMIC_LEAF:
                length = int.from_bytes(input_data[offset:offset + 32], byteorder='big')
                if slice:
                    start = slice.start if slice.start >= 0 else length + slice.start
                    end = slice.end if slice.end >= 0 else length + slice.end

                    if start < 0 or end < 0 or start >= length or end >= length:
                        raise ValueError("Slice out of bounds")
                    
                    return input_data[offset + 32 + start:offset + 32 + end]
                return input_data[offset + 32:offset + 32 + length]
    #raise ValueError("Path did not resolve to a leaf element")
    pass

test_cases = [ 
    {
        "abi_file": "tests/abi.json",
        "functions": [
            {
                "name": "test_static",
                "input_file": "tests/input_test_static.data",
                "paths": ["p1", "p2", "p3", "p3.[0]", "p3.[-1]", "p4.a", "p4.b.[0]", "p4.b.[1]", "p4.b.[-1]", "p4.b.[0:1]"]
            },
            {
                "name": "test_dynamic",
                "input_file": "tests/input_test_dynamic.data",
                "paths": ["p1", "p1.[0:5]", "p2", "p2.[0]", "p2.[1]", "p2.[-1]", "p3", "p3.c", "p3.c.[-3:-1]"]
            },
            {
                "name": "test_array2",
                "input_file": "tests/input_test_array2.data",
                "paths": ["p1", 
                          "p1.[0].[0].[0]", "p1.[0].[0].[1]", 
                          "p1.[0].[1].[0]", "p1.[0].[1].[1]", 
                          "p1.[0].[2].[0]", "p1.[0].[2].[1]", 
                          "p1.[1].[0].[0]", "p1.[1].[0].[1]", 
                          "p1.[0].[0].[-1]",
                          "p1.[0].[-1].[0]", "p1.[0].[-2].[0]",
                          "p1.[-1].[0].[0]" ]
            }
            # Add more functions and their paths here if needed
        ]
    }
]

for test in test_cases:
    with open(test['abi_file'], 'r') as file:
        json_data = file.read()

    abi = parse_json(json_data)

    print(f"ABI {test['abi_file']}:")
    for function in abi:
        print(function)

    for function in test['functions']:

        with open(function['input_file'], 'r') as file:
            input_data = file.read()

        if input_data.startswith("0x"):
            input_data = input_data[10:]
        input_data_bytes = bytes.fromhex(input_data)


        # find function with name "test_static"
        abi_function = next((func for func in abi if func.name == function['name']), None)
        paths = function['paths']

        for p in paths:
            parsed_path = build_path(p, abi_function)
            print(f"Path {p}:\n\tBinary_repr: {parsed_path.to_string()}\n\tTLV: {parsed_path.to_bytes()}")
            value = apply_path(parsed_path, input_data_bytes)
            print(f"\tValue: {value.hex() if value else 'Array or struct'}")
