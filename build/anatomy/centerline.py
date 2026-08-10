"""
centerline.py — turn a tubular anatomical surface mesh into an ordered centerline polyline.

Why not PCA or a bounding-box axis: the structures that matter here are curved (the aorta is a
candy cane) and some of them branch (the pulmonary artery, the coronaries). A straight-axis
method fails on both.

Method — geodesic binning:
  1. Build the mesh's edge graph, weighted by edge length.
  2. Dijkstra from a seed vertex at the vessel's proximal end, giving each vertex its
     *along-the-surface* distance from that end.
  3. Bin vertices by that distance. Each bin is a ring around the tube; its centroid is a
     point on the centerline. Curvature is handled for free because distance follows the wall.
  4. Within a bin, split into connected components. One component means one lumen; two means
     the vessel has branched. That makes branching fall out of the same pass rather than
     needing a special case.
  5. Link each component to the component in the previous bin it shares the most edges with,
     giving a tree of segments.

The centroid of a ring is the lumen centre only when the ring is roughly perpendicular to the
tube, which geodesic distance guarantees away from sharp bends. Near tight bends the centroid
pulls slightly toward the inside of the curve; `smooth()` takes that out.
"""

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components, dijkstra


def _edge_graph(mesh):
    """Sparse |V|x|V| matrix of edge lengths."""
    e = mesh.edges_unique
    v = mesh.vertices
    w = np.linalg.norm(v[e[:, 0]] - v[e[:, 1]], axis=1)
    n = len(v)
    g = coo_matrix((np.r_[w, w], (np.r_[e[:, 0], e[:, 1]], np.r_[e[:, 1], e[:, 0]])), shape=(n, n))
    return g.tocsr()


def seed_vertex(mesh, axis=2, sign=-1):
    """
    The vertex to start tracing from — the vessel's proximal end.

    sign=-1 takes the minimum along `axis`, +1 the maximum, and 0 the vertex nearest the mean
    along that axis (used where the proximal end is in the middle, as for the pulmonary veins
    converging on the left atrium).
    """
    v = mesh.vertices[:, axis]
    if sign == 0:
        return int(np.argmin(np.abs(v - v.mean())))
    return int(np.argmax(sign * v))


def _components_in_bin(graph, idx):
    """Connected components of the sub-graph induced by vertex indices `idx`."""
    sub = graph[idx][:, idx]
    n, lab = connected_components(sub, directed=False)
    return [idx[lab == k] for k in range(n)]


def trace_single(mesh, seed=None, bins=48, min_bin_vertices=6, mask=None, max_dist=None):
    """
    Centerline of a vessel treated as a single course: one point per geodesic bin, taken over
    *all* selected vertices in that bin.

    Prefer this over `trace()` whenever the course is a simple tube. These meshes are open
    surfaces, so a ring can legitimately arrive as two connected components (the wall is cut).
    Splitting it would place the "centre" on one wall instead of in the lumen. Averaging the
    whole ring is both simpler and more accurate here.

    `mask` restricts which vertices participate — used to pull one named course out of a mesh
    that carries several, e.g. taking only the subject's-right side of the pulmonary artery.
    `max_dist` stops the trace at a geodesic distance from the seed, which is how the
    extrapulmonary portion of a vessel is separated from its intrapulmonary ramification: the
    app's "R. Pulmonary Artery" means the vessel up to the hilum, not every branch beyond it.
    """
    if seed is None:
        seed = seed_vertex(mesh)
    dist = dijkstra(_edge_graph(mesh), indices=seed, directed=False)
    ok = np.isfinite(dist)
    if mask is not None:
        ok = ok & mask
    if ok.sum() < min_bin_vertices:
        raise ValueError("mask leaves too few reachable vertices")
    dmax = dist[ok].max()
    if max_dist is not None:
        dmax = min(dmax, float(max_dist))
        ok = ok & (dist <= dmax)
    if not dmax > 0:
        raise ValueError("degenerate mesh: zero geodesic extent")
    step = dmax / bins
    pts = []
    for b in range(bins):
        idx = np.where(ok & (dist >= b * step) & (dist < (b + 1) * step))[0]
        if len(idx) >= min_bin_vertices:
            pts.append(mesh.vertices[idx].mean(axis=0))
    if len(pts) < 2:
        raise ValueError("too few usable bins for a centerline")
    return np.array(pts)


def trace_axis(mesh, axis=0, sign=+1, bins=24, min_bin_vertices=6):
    """
    Centerline by slabbing along a coordinate axis: one point per slab, ordered by `sign`.

    Use where a vessel's course is dominated by one direction and the mesh carries branches
    that geodesic binning would zig-zag between — the pulmonary arteries and veins run laterally
    from the midline to the hilum while shedding branches the whole way, so a geodesic ring
    centroid hops from one branch to another and inflates the path. Slabbing along X follows the
    lateral course and averages the branches out instead.
    """
    v = mesh.vertices
    lo, hi = float(v[:, axis].min()), float(v[:, axis].max())
    if not hi > lo:
        raise ValueError("degenerate extent along the requested axis")
    edges = np.linspace(lo, hi, bins + 1)
    pts = []
    for b in range(bins):
        idx = np.where((v[:, axis] >= edges[b]) & (v[:, axis] < edges[b + 1]))[0]
        if len(idx) >= min_bin_vertices:
            pts.append(v[idx].mean(axis=0))
    if len(pts) < 2:
        raise ValueError("too few usable slabs for a centerline")
    pts = np.array(pts)
    return pts if sign > 0 else pts[::-1]


def radius_profile(mesh, points):
    """Distance from each centerline point to the nearest surface point — the local radius."""
    import trimesh
    q = trimesh.proximity.ProximityQuery(mesh)
    return np.abs(q.signed_distance(points)) if mesh.is_watertight else \
        np.linalg.norm(mesh.vertices[q.vertex(points)[1]] - points, axis=1)


def trace(mesh, seed=None, bins=48, min_bin_vertices=6):
    """
    Trace the centerline tree.

    Returns a list of segments, each a dict:
        points      (m,3) ordered centerline points, proximal -> distal
        parent      index of the parent segment, or None for the trunk
        start_bin   bin index where the segment begins
    Segment 0 is always the trunk containing the seed.
    """
    if seed is None:
        seed = seed_vertex(mesh)
    graph = _edge_graph(mesh)
    dist = dijkstra(graph, indices=seed, directed=False)
    finite = np.isfinite(dist)
    if finite.sum() < min_bin_vertices:
        raise ValueError("mesh has no connected neighbourhood around the seed")
    dmax = dist[finite].max()
    if not dmax > 0:
        raise ValueError("degenerate mesh: zero geodesic extent")
    step = dmax / bins

    # bin -> list of node ids; node_of_vertex lets the linking step stay vectorized.
    nodes = []          # {bin, centroid}
    per_bin = []
    node_of_vertex = np.full(len(mesh.vertices), -1, dtype=np.int64)
    for b in range(bins):
        lo, hi = b * step, (b + 1) * step
        idx = np.where(finite & (dist >= lo) & (dist < hi))[0]
        if len(idx) < min_bin_vertices:
            per_bin.append([])
            continue
        comps = [c for c in _components_in_bin(graph, idx) if len(c) >= min_bin_vertices]
        ids = []
        for c in comps:
            nid = len(nodes)
            ids.append(nid)
            node_of_vertex[c] = nid
            nodes.append({"bin": b, "centroid": mesh.vertices[c].mean(axis=0)})
        per_bin.append(ids)

    if not nodes:
        raise ValueError("no usable bins — mesh too small for the requested bin count")

    # Count edges between every pair of nodes in one vectorized pass over the edge list, then
    # link each node to the earlier-bin node it shares the most edges with.
    e = mesh.edges_unique
    na, nb = node_of_vertex[e[:, 0]], node_of_vertex[e[:, 1]]
    keep = (na >= 0) & (nb >= 0) & (na != nb)
    pair_count = {}
    for a, c in zip(na[keep], nb[keep]):
        k = (int(a), int(c)) if a < c else (int(c), int(a))
        pair_count[k] = pair_count.get(k, 0) + 1

    shared = {}
    for (a, c), n in pair_count.items():
        shared.setdefault(a, {})[c] = n
        shared.setdefault(c, {})[a] = n

    parent = {}
    for b in range(1, bins):
        prev = per_bin[b - 1]
        if not prev:                               # bridge across empty bins
            prev = next((per_bin[pb] for pb in range(b - 2, -1, -1) if per_bin[pb]), [])
        if not prev:
            continue
        prev_set = set(prev)
        for i in per_bin[b]:
            cand = {j: n for j, n in shared.get(i, {}).items() if j in prev_set}
            if cand:
                parent[i] = max(cand, key=cand.get)
            else:                                  # fall back to nearest centroid
                parent[i] = min(prev, key=lambda j: float(np.linalg.norm(nodes[j]["centroid"] - nodes[i]["centroid"])))

    # Walk the tree into segments: a new segment starts at the root or wherever a node has
    # siblings (i.e. its parent has more than one child).
    children = {}
    for c, p in parent.items():
        children.setdefault(p, []).append(c)
    roots = [i for i in range(len(nodes)) if i not in parent]
    roots.sort(key=lambda i: nodes[i]["bin"])

    segments = []

    def walk(start, parent_seg):
        chain = [start]
        cur = start
        while True:
            kids = children.get(cur, [])
            if len(kids) == 1:
                cur = kids[0]
                chain.append(cur)
            else:
                break
        seg_id = len(segments)
        segments.append({
            "points": np.array([nodes[i]["centroid"] for i in chain]),
            "parent": parent_seg,
            "start_bin": nodes[chain[0]]["bin"],
        })
        for k in children.get(chain[-1], []):
            walk(k, seg_id)

    walk(roots[0], None)
    for r in roots[1:]:                            # disconnected islands, kept but flagged last
        walk(r, None)
    return segments


def longest_path(segments):
    """Points along the geometrically longest root-to-leaf path — the vessel's main course."""
    kids = {}
    for i, s in enumerate(segments):
        kids.setdefault(s["parent"], []).append(i)

    def length(pts):
        return float(np.linalg.norm(np.diff(pts, axis=0), axis=1).sum()) if len(pts) > 1 else 0.0

    best = {"len": -1.0, "pts": None}

    def walk(i, acc):
        pts = np.vstack([acc, segments[i]["points"]]) if len(acc) else segments[i]["points"]
        ch = kids.get(i, [])
        if not ch:
            if length(pts) > best["len"]:
                best.update(len=length(pts), pts=pts)
            return
        for c in ch:
            walk(c, pts)

    for r in kids.get(None, []):
        walk(r, np.empty((0, 3)))
    return best["pts"]


def path_to_extreme(segments, axis=0, sign=+1):
    """
    Root-to-leaf path ending at the segment that reaches furthest along `axis`.

    This is how a named branch of a forking vessel is picked — the right pulmonary artery is
    simply "the path that gets furthest into the right hemithorax". Walking the segment tree by
    parent index is more robust than inspecting a segment's immediate children, because a
    surface mesh throws off short spurious splits near the fork that are not real branches.
    """
    if not segments:
        return np.empty((0, 3))
    reach = [float((sign * s["points"][:, axis]).max()) if len(s["points"]) else -np.inf
             for s in segments]
    leaf = int(np.argmax(reach))
    chain = []
    i = leaf
    seen = set()
    while i is not None and i not in seen:
        seen.add(i)
        chain.append(i)
        i = segments[i]["parent"]
    chain.reverse()
    return np.vstack([segments[i]["points"] for i in chain])


def smooth(points, passes=2):
    """Laplacian smoothing with fixed endpoints — removes the inward bias at tight bends."""
    p = np.array(points, dtype=float)
    for _ in range(passes):
        if len(p) < 3:
            break
        q = p.copy()
        q[1:-1] = 0.25 * p[:-2] + 0.5 * p[1:-1] + 0.25 * p[2:]
        p = q
    return p


def resample(points, n):
    """Resample a polyline to `n` points evenly spaced by arc length."""
    p = np.asarray(points, dtype=float)
    if len(p) < 2:
        return p
    seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    if s[-1] <= 0:
        return p[:1].repeat(n, axis=0)
    t = np.linspace(0.0, s[-1], n)
    return np.column_stack([np.interp(t, s, p[:, k]) for k in range(3)])
