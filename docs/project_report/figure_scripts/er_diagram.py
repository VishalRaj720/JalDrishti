"""Draw the ER diagrams of the JalDrishti database from a live, fully migrated schema.

    cd backend && alembic upgrade head            # any empty PostgreSQL + PostGIS database
    DATABASE_URL=postgresql://user@host:port/db python docs/project_report/figure_scripts/er_diagram.py

Writes, into docs/project_report/figures/:
    er_overview.png        every table and every foreign key as crow's-foot relationships (Section 8.6)
    er_full_<part>.png     every column of every table, in four page-sized parts; each foreign-key
                           column names the table it points to (Annexure A)

Nothing is typed by hand: tables, columns, types, nullability, primary and foreign keys
are read from information_schema, so the diagram is the schema the migrations produce.
Requires Graphviz (`dot`) and psycopg2.
"""
import os
import re
import subprocess
from collections import defaultdict
from pathlib import Path

import psycopg2

OUT = Path(__file__).resolve().parents[1] / "figures"
SKIP = {"alembic_version", "spatial_ref_sys", "geography_columns", "geometry_columns"}

# Domain of each table: drives the header colour and the split of the full diagram.
# A table added by a later migration must be placed here (and in GRID) or the script stops.
GROUPS = {
    "geography": ("Geography and measured data", "#DCEBF7", [
        "districts", "blocks", "aquifers", "monitoring_stations", "groundwater_level_readings",
        "monitoring_wells", "water_samples", "data_sources", "dataset_versions"]),
    "modelling": ("Modelling, field data and publication", "#E3F1DF", [
        "isr_points", "scenarios", "simulation_runs", "simulations", "advisories",
        "ore_observations", "field_observations"]),
    "people": ("Users, alerts and audit", "#FBE9D7", [
        "orgs", "users", "alerts", "alert_reads", "alert_deliveries", "block_subscriptions",
        "audit_log"]),
}
# The complete (column-level) diagram is split so each figure fits one A4 page at a readable size.
FULL_FIGURES = {
    "geography": GROUPS["geography"][2],
    "modelling": ["isr_points", "scenarios", "simulation_runs", "simulations"],
    "publication": ["advisories", "ore_observations", "field_observations"],
    "people": GROUPS["people"][2],
}
GROUP_OF = {t: g for g, (_, _, ts) in GROUPS.items() for t in ts}

TYPE_SHORT = {
    "character varying": "varchar", "timestamp with time zone": "timestamptz",
    "timestamp without time zone": "timestamp", "double precision": "float8",
    "integer": "int", "boolean": "bool", "USER-DEFINED": "enum",
}


def read_schema(dsn):
    con = psycopg2.connect(dsn)
    cur = con.cursor()
    cur.execute("""
        select c.table_name, c.column_name, c.data_type, c.udt_name, c.is_nullable
        from information_schema.columns c
        where c.table_schema = 'public' order by c.table_name, c.ordinal_position""")
    cols = defaultdict(list)
    for t, c, dt, udt, nullable in cur.fetchall():
        if t in SKIP:
            continue
        if dt == "USER-DEFINED":
            typ = udt
        elif dt == "ARRAY":
            typ = udt.lstrip("_") + "[]"
        else:
            typ = TYPE_SHORT.get(dt, dt)
        cols[t].append([c, typ, nullable == "YES"])
    cur.execute("select f_table_name, f_geometry_column, type from geometry_columns")
    geom = {(t, c): g.lower() for t, c, g in cur.fetchall()}
    for t, cs in cols.items():
        for col in cs:
            if (t, col[0]) in geom:
                col[1] = f"geometry({geom[(t, col[0])]})"
    cur.execute("""
        select tc.table_name, k.column_name from information_schema.table_constraints tc
        join information_schema.key_column_usage k
          on tc.constraint_name = k.constraint_name and tc.table_schema = k.table_schema
        where tc.constraint_type = 'PRIMARY KEY' and tc.table_schema = 'public'""")
    pks = defaultdict(set)
    for t, c in cur.fetchall():
        pks[t].add(c)
    cur.execute("""
        select tc.table_name, k.column_name, ccu.table_name, ccu.column_name
        from information_schema.table_constraints tc
        join information_schema.key_column_usage k
          on tc.constraint_name = k.constraint_name and tc.table_schema = k.table_schema
        join information_schema.constraint_column_usage ccu
          on ccu.constraint_name = tc.constraint_name and ccu.table_schema = tc.table_schema
        where tc.constraint_type = 'FOREIGN KEY' and tc.table_schema = 'public'
        order by 1, 2""")
    fks = [r for r in cur.fetchall() if r[0] not in SKIP]
    con.close()
    return cols, pks, fks


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# Overview layout: hand-placed so the hub tables (users, blocks, isr_points) sit in the middle
# and no relationship line has to cross a table. Columns are domains read left to right.
GRID = [
    ["districts", "aquifers", "monitoring_stations", "groundwater_level_readings"],
    ["block_subscriptions", "blocks", "monitoring_wells", "water_samples"],
    ["alerts", "users", "field_observations", "data_sources"],
    ["alert_reads", "alert_deliveries", "orgs", "dataset_versions"],
    ["audit_log", "advisories", "scenarios", "simulation_runs"],
    ["ore_observations", "simulations", "isr_points", None],
]
COL_X = [0, 175, 360, 625]      # points
ROW_Y = 125
X_SHIFT = {"groundwater_level_readings": 70}   # the two longest names share the top row


def name_node(t, cols, pos):
    colour = GROUPS[GROUP_OF[t]][1]
    return (f'"{t}" [pos="{pos[0]},{pos[1]}!", label=<<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" '
            f'CELLPADDING="4" COLOR="#888888"><TR><TD BGCOLOR="{colour}"><B>{esc(t)}</B></TD></TR>'
            f'<TR><TD><FONT POINT-SIZE="10" COLOR="#555555">{len(cols[t])} columns</FONT></TD></TR></TABLE>>];')


def column_card(t, cols, pks, refs):
    """Every column: key marker, name, type; a foreign key also names its target table."""
    colour = GROUPS[GROUP_OF[t]][1]
    rows = []
    for name, typ, nullable in cols[t]:
        key = "PK" if name in pks[t] else ("FK" if name in refs[t] else "")
        mark = f'<FONT POINT-SIZE="8" COLOR="#555555">{key}</FONT>' if key else " "
        nm = f"<B>{esc(name)}</B>" if key == "PK" else (f"<I>{esc(name)}</I>" if key == "FK" else esc(name))
        typ_txt = esc(typ) + ("" if nullable or key == "PK" else " *")
        if key == "FK":
            typ_txt += f' <FONT COLOR="#1F4E79">&#8594; {esc(refs[t][name])}</FONT>'
        rows.append(f'<TR><TD ALIGN="LEFT">{mark}</TD><TD ALIGN="LEFT">{nm}</TD>'
                    f'<TD ALIGN="LEFT"><FONT COLOR="#555555">{typ_txt}</FONT></TD></TR>')
    return (f'"{t}" [label=<<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" CELLPADDING="2" COLOR="#888888">'
            f'<TR><TD COLSPAN="3" BGCOLOR="{colour}"><B>{esc(t)}</B></TD></TR>{"".join(rows)}</TABLE>>];')


def edges(fks, cols):
    out = []
    for child, col, parent, _ in fks:
        nullable = next(c[2] for c in cols[child] if c[0] == col)
        # crow's foot: many on the child side; exactly one on the parent side, or zero-or-one
        # when the foreign key may be empty
        out.append(f'"{child}" -> "{parent}" '
                   f'[dir=both, arrowtail=crow, arrowhead={"teeodot" if nullable else "teetee"}];')
    return out


def render(name, body, engine, graph_attrs, rotate=True):
    dot = ('digraph ER { graph [fontname="Helvetica", dpi=200, ' + graph_attrs + ']; '
           'node [shape=plaintext, fontname="Helvetica", fontsize=12]; '
           'edge [color="#4A4A4A", penwidth=1.1, arrowsize=0.8];\n' + "\n".join(body) + "\n}")
    src = OUT / f"{name}.dot"
    src.write_text(dot)
    subprocess.run([engine, "-Tpng", str(src), "-o", str(OUT / f"{name}.png")], check=True)
    src.unlink()
    fit_page(OUT / f"{name}.png", allow_rotate=rotate)


def fit_page(png, box=(16.0, 22.0), dpi=200, allow_rotate=True):
    """Turn a wide figure by 90 degrees only when that prints it at least 25 % larger."""
    from PIL import Image
    im = Image.open(png)
    w, h = (im.width / dpi * 2.54, im.height / dpi * 2.54)          # cm at 100 %
    upright = min(box[0] / w, box[1] / h, 1.0)
    turned = min(box[0] / h, box[1] / w, 1.0)
    rotate = allow_rotate and turned > upright * 1.25
    if rotate:
        im.rotate(90, expand=True).save(png)
    print(f"wrote {png.name}: {'rotated, ' if rotate else ''}12 pt text prints at "
          f"{12 * (turned if rotate else upright):.1f} pt")


def card_sizes(cards):
    """Width and height (points) of each card, as Graphviz lays it out."""
    dot = ('digraph S { graph [dpi=72]; node [shape=plaintext, fontname="Helvetica", fontsize=12]; '
           + " ".join(cards.values()) + "}")
    plain = subprocess.run(["dot", "-Tplain"], input=dot, capture_output=True, text=True, check=True).stdout
    sizes = {}
    for line in plain.splitlines():
        f = line.split()
        if f and f[0] == "node":
            sizes[f[1].strip('"')] = (float(f[4]) * 72, float(f[5]) * 72)
    return sizes


def packed(cards, gap=14, page=(16.0, 22.0)):
    """Masonry layout: cards top-aligned in columns, keeping table order; the column count is the one
    that prints largest on the page."""
    sizes = card_sizes(cards)
    best = None
    for k in (2, 3, 4):
        columns = [[] for _ in range(k)]
        heights = [0.0] * k
        for t in cards:                                    # next card into the shortest column
            i = heights.index(min(heights))
            columns[i].append(t)
            heights[i] += sizes[t][1] + gap
        widths = [max((sizes[t][0] for t in col), default=0) for col in columns]
        w, h = sum(widths) + gap * (k - 1), max(heights)
        scale = min(page[0] / (w / 72 * 2.54), page[1] / (h / 72 * 2.54))
        if best is None or scale > best[0]:
            best = (scale, columns, widths)
    _, columns, widths = best
    body, x = [], 0.0
    for col, cw in zip(columns, widths):
        y = 0.0
        for t in col:
            w, h = sizes[t]
            # neato -n positions are node centres, in points; y grows upwards
            body.append(cards[t][:-2] + f', pos="{x + w / 2:.1f},{-(y + h / 2):.1f}!"];')
            y += h + gap
        x += cw + gap
    return body


def main():
    dsn = re.sub(r"^postgresql\+\w+://", "postgresql://", os.environ["DATABASE_URL"])
    cols, pks, fks = read_schema(dsn)
    placed = {t for row in GRID for t in row if t}
    missing = sorted((set(cols) - placed) | (set(cols) - set(GROUP_OF)))
    if missing:
        raise SystemExit(f"tables not placed in GROUPS/GRID: {missing}")
    print(f"{len(cols)} tables, {sum(len(c) for c in cols.values())} columns, {len(fks)} foreign keys")
    refs = defaultdict(dict)
    for child, col, parent, _ in fks:
        refs[child][col] = parent

    body = [name_node(t, cols, (COL_X[c] + X_SHIFT.get(t, 0), -r * ROW_Y))
            for r, row in enumerate(GRID) for c, t in enumerate(row) if t]
    render("er_overview", body + edges(fks, cols), "neato", 'splines=true, overlap=false, inputscale=0',
           rotate=False)                                  # read in the chapter, so kept upright

    in_full = sorted(t for ts in FULL_FIGURES.values() for t in ts)
    if in_full != sorted(cols):
        raise SystemExit("FULL_FIGURES must hold every table exactly once")
    for g, ts in FULL_FIGURES.items():
        cards = {t: column_card(t, cols, pks, refs) for t in ts}
        render(f"er_full_{g}", packed(cards), "neato", "splines=false, inputscale=0")

if __name__ == "__main__":
    main()
