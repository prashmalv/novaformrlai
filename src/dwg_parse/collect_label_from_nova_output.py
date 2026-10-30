import re

# L-shaped column format: L-COL:-(400X3000)+(400X1500)
_L_COL_RE = re.compile(
    r'^(?!H[-\s]*\d(?:[-\s]|$))'
    r'(?:(GF|FF|SF|TF|RF|BF|LG|PH|B[0-9]|[1-9][0-9]*[FA])[-\s]*)?'
    r'L[-\s]*COL[:\-\s]*'                       # L-COL + separator
    r'\((\d+)\s*[xX]\s*(\d+)\)'               # (W1xH1)  first leg
    r'\s*\+\s*'                                # +
    r'\((\d+)\s*[xX]\s*(\d+)\)',              # (W2xH2)  second leg
    re.IGNORECASE,)


_SHEAR_WALL_LABEL_RE = re.compile(
    r'^([A-GI-Z]{1,2})[-_\s]*\d+[-_\s]+(\d+)\s*[xX]\s*(\d+)$',
    re.IGNORECASE,)

pattern =   r'^[A-Z]{1,4}[-_  ]?\d{1,3}$'     #r'^[A-ZA-Z]{1,2}[-_ ]?[1-3]$'




_NOVA_LABEL_RE = re.compile(
    # Floor prefix: named (GF/FF/SF/TF/RF/BF/LG/PH) OR basement B1-B9
    # OR numbered floors 1F-99F / 1A-9A — deliberately excludes bare R/L
    # to avoid consuming R-COL / L-COL type prefixes
    r'^(?!H[-\s]*\d(?:[-\s]|$))'
    r'(?:(GF|FF|SF|TF|RF|BF|LG|PH|B[0-9]|[1-9][0-9]*[FA])[-\s]*)?'
    r'(R[-\s]*COL|L[-\s]*COL|COL)'             # element type
    r'[:\-\s]+'                                 # separator (colon, dash, space)
    r'[Ø\s]*'                                   # optional Ø (R-COL diameter symbol)
    r'(\d+)\s*[xX]\s*(\d+)',                    # WxD dimensions
    re.IGNORECASE,)



def collect_labels(all_texts,col_labels, seen_pos) ->list[dict]:
    for tx, ty, txt in all_texts:
        pos_key = (round(tx), round(ty))
        if pos_key in seen_pos:
            continue

        # Skip elevation-view labels (e.g. "COL ELEVATION: 600X300")
        # These appear in the side-view section, not the plan view
        if re.search(r'\bELEV(ATION)?\b', txt, re.IGNORECASE):
            continue

        # L-COL parentheses format first: L-COL:-(400X3000)+(400X1500)
        m2 = _L_COL_RE.search(txt)
        if m2:
            floor_str = (m2.group(1) or "").upper()
            leg1_w, leg1_h = int(m2.group(2)), int(m2.group(3))
            leg2_w, leg2_h = int(m2.group(4)), int(m2.group(5))
            seen_pos.add(pos_key)
            col_labels.append({
                'x': tx, 'y': ty, 'raw_text': txt,
                'floor': floor_str, 'etype': 'LCOL',
                'is_lcol_paren': True,
                'leg1_w': leg1_w, 'leg1_h': leg1_h,
                'leg2_w': leg2_w, 'leg2_h': leg2_h,
                'dim1': max(leg1_w, leg1_h, leg2_w, leg2_h),
                'dim2': min(leg1_w, leg2_w),
            })
            continue
        m1 = _SHEAR_WALL_LABEL_RE.search(txt)
        if m1:
            etype_raw = m1.group(1 or '').upper()
            dim1 = int(m1.group(2))
            dim2 = int(m1.group(3))
            seen_pos.add(pos_key)
            col_labels.append({
                'x': tx, 'y': ty, 'raw_text': txt,
                'floor': '',
                'etype': etype_raw,
                'is_lcol_paren': False,
                'dim1': dim1, 'dim2': dim2,
            })
            continue
        # pattern for without dimension label
        pttern = bool(re.fullmatch(pattern, txt))
        if pttern:
            col_labels.append({
                'x': tx, 'y': ty, 'raw_text': txt,
                'floor': '',
                'etype': '',
                'is_lcol_paren': False,
                'dim1': 0, 'dim2': 0,
            })
            continue

        # Regular / R-COL / plain L-COL format
        m = _NOVA_LABEL_RE.search(txt)
        if not m:
            continue
        floor_str = (m.group(1) or "").upper()
        etype_raw = m.group(2).upper().replace(" ", "").replace("-", "")
        dim1 = int(m.group(3))
        dim2 = int(m.group(4))
        seen_pos.add(pos_key)
        col_labels.append({
            'x': tx, 'y': ty, 'raw_text': txt,
            'floor': floor_str, 'etype': etype_raw,
            'is_lcol_paren': False,
            'dim1': dim1, 'dim2': dim2,
        })

    return col_labels
