def _cluster_rows(ys: list, tol: float = 280) -> list:
    """Group nearby Y values into clusters; return sorted (desc) centroid per cluster."""
    if not ys:
        return []
    sorted_ys = sorted(ys, reverse=True)
    clusters = [[sorted_ys[0]]]
    for y in sorted_ys[1:]:
        if abs(clusters[-1][-1] - y) <= tol:
            clusters[-1].append(y)
        else:
            clusters.append([y])
    return [sum(c) / len(c) for c in clusters]