"""Small GLB utilities shared by asset preparation and geometry QA."""

import numpy as np
from pygltflib import Accessor, BufferView


def read_accessor(glb, index):
    a = glb.accessors[index]
    view = glb.bufferViews[a.bufferView]
    dtype = np.dtype({5126: np.float32, 5125: np.uint32, 5123: np.uint16, 5121: np.uint8}[a.componentType])
    width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}[a.type]
    if a.sparse:
        raise ValueError("Sparse accessors need a dedicated importer")
    return np.ndarray(
        (a.count, width),
        dtype=dtype,
        buffer=glb.binary_blob(),
        offset=(view.byteOffset or 0) + (a.byteOffset or 0),
        strides=(view.byteStride or dtype.itemsize * width, dtype.itemsize),
    ).copy()


def add_vec3(glb, value):
    value = np.asarray(value, dtype=np.float32)
    blob = bytearray(glb.binary_blob())
    blob.extend(b"\0" * ((-len(blob)) % 4))
    view = len(glb.bufferViews)
    glb.bufferViews.append(BufferView(buffer=0, byteOffset=len(blob), byteLength=value.nbytes, target=34962))
    blob.extend(value.tobytes())
    index = len(glb.accessors)
    glb.accessors.append(
        Accessor(
            bufferView=view,
            componentType=5126,
            count=len(value),
            type="VEC3",
            min=value.min(0).tolist(),
            max=value.max(0).tolist(),
        )
    )
    glb.buffers[0].byteLength = len(blob)
    glb.set_binary_blob(bytes(blob))
    return index


def add_array(glb, value, kind, component=5126, target=34962):
    dtype = {5126: np.float32, 5125: np.uint32, 5123: np.uint16}[component]
    value = np.ascontiguousarray(value, dtype=dtype)
    blob = bytearray(glb.binary_blob())
    blob.extend(b"\0" * ((-len(blob)) % 4))
    view = len(glb.bufferViews)
    glb.bufferViews.append(BufferView(buffer=0, byteOffset=len(blob), byteLength=value.nbytes, target=target))
    blob.extend(value.tobytes())
    index = len(glb.accessors)
    glb.accessors.append(Accessor(bufferView=view, componentType=component, count=len(value), type=kind))
    glb.buffers[0].byteLength = len(blob)
    glb.set_binary_blob(bytes(blob))
    return index


def joint_world_positions(glb):
    parents = {child: i for i, n in enumerate(glb.nodes) for child in n.children or []}
    cache = {}

    def position(i):
        if i not in cache:
            node = glb.nodes[i]
            # AniGen exports translation-only rest joints; reject a different convention.
            if node.matrix or node.rotation not in (None, [], [0, 0, 0, 1]):
                raise ValueError("Non-translation rest skeleton needs a transform-aware importer")
            cache[i] = np.array(node.translation or [0, 0, 0]) + (position(parents[i]) if i in parents else 0)
        return cache[i]

    return {i: position(i) for i in glb.skins[0].joints}
