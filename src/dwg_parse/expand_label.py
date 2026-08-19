import re


def _expand_label(label: str) -> list:
    """
    Expand compound schedule labels.
    "C7,C8"       → ["C7", "C8"]
    "SW5 TO SW11" → ["SW5","SW6","SW7","SW8","SW9","SW10","SW11"]
    """
    label = label.strip().upper().replace('%%U', '')
    # rm = re.match(r'^([A-Z]+)(\d+)\s+TO\s+[A-Z]*(\d+)([A-Z]?)$', label)
    rm = re.match(r'^(?!H-?\d)([A-Z]+)-?(\d+)\s+TO\s+[A-Z]*-?(\d+)([A-Z]?)$',label)
    if rm:
        prefix = rm.group(1)
        start, end = int(rm.group(2)), int(rm.group(3))
        return [f"{prefix}{i}" for i in range(start, end + 1)]
    if ',' in label:
        parts = [p.strip() for p in label.split(',')]
        result, last_pfx = [], ''
        for p in parts:
            # m2 = re.match(r'^([A-Z]*)(\d+[A-Z]?)$', p)
            m2 = re.match(r'^(?!H-?\d)([A-Z]*)-?(\d+[A-Z]?)$', p)
            if m2:
                if m2.group(1):
                    last_pfx = m2.group(1)
                result.append(f"{last_pfx}{m2.group(2)}")
            else:
                result.append(p)
        return result
    return [label]