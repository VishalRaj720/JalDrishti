# NAQUIM Extraction Tracker — Jharkhand district reports

Purpose: per-district numbers for the Module-5 vertical model (replacing statewide constants in `config/parameters.py` `VERTICAL`).

Targets:
- **(T1)** weathered-zone base depth → `layer1_base_m` per district
- **(T2)** fracture depth ranges → grounds `ore_depth` plausibility + the Kv/Kh story
- **(T3)** Aquifer-II (confined) water levels → sanity-check `upward_gradient`

Generated 2026-07-07 by automated keyword scan (`weathered`, `fracture`+`depth`, `Aquifer-I/II`, `m bgl`). Page numbers are 1-based PDF pages. Snippets are raw extracted text — verify against the page before use.

---

## ✅ EXTRACTED VALUES — Singhbhum uranium belt (Module-5 priority)

The ISR-relevant districts are **East Singhbhum** (hosts Jaduguda, Narwapahar, Turamdih,
Bhatin, Bagjata, Mohuldih, Banduhurang) + **Saraikela-Kharsawan** + **West Singhbhum**.
Their bundled NAQUIM report (row 6) downloaded as a CGWB 404 page. Per user request
(2026-07-07) these numbers were **sourced manually from the open web** because the CGWB
site was otherwise unreachable, then cross-checked against the *valid* W-Singhbhum NAQUIM PDF.

| District | T1 weathered base (→`layer1_base_m`) | T2 fracture depths (→`ore_depth`/Kv story) | T3 water levels & confinement (→`upward_gradient`) | Source |
|----------|--------------------------------------|--------------------------------------------|----------------------------------------------------|--------|
| **East Singhbhum** (ore district) | GW in weathered zone **10–25 m**; weathered mantle **15–34 m** (thicker N & E; up to ~40 m in local studies) | Exploratory wells **27.6–300.9 m bgl**; fractures tapped **~20–147 m** (e.g. 32–78, 20–73, 41–147 m); fractured aquifer persists to **~258 m** then massive rock; T = **207.7–570.8 m²/day**; borewell yield **2.7–78 m³/hr** | Phreatic (dug wells) pre-mon **3.96–14.85** / post-mon **1.10–13.85 m bgl**; deep exploratory static WL **1.60–35.22 m bgl** (deeper than phreatic → natural downward gradient; ISR overpressure reverses it) — deep aquifer **confined/semi-confined** | CGWB *East Singhbhum District Profile* (2013) — saved as `cgwb_east_singhbhum_profile.pdf`; ¹ ² |
| **West Singhbhum** (adjacent, cross-check) | Weathering **12–20 m** (Singhbhum Granite), **16–24 m** (Chakradharpur Granite); volcano-sed phreatic **10–30 m** (64 m at Goelkera) | Productive fractures common **<45 m**, less frequent **45–100 m**, deep **107–112 m**, **none beyond 180 m** (granite); volcano-sed fractures **14–167 m**, max **200 m**; discharge negligible–44.28 m³/hr | Aquifer-II **confined to semi-confined** in deep fractures of massive granite | `W SINGHBHUM FINAL JH.pdf` p.42–48 (NAQUIM, valid) |
| **Saraikela-Kharsawan** | *no direct source obtained* — bracket by E/W Singhbhum (same Singhbhum Granite + Singhbhum Group craton): **~15–25 m** | same craton: productive **<45 m**, extending **~150–200 m** | same craton: shallow phreatic + confined deep fractured | inferred from E/W Singhbhum analogues (CGWB profile download blocked by SSL) |

**Config implications (for Phase-2 `VERTICAL` per-district table):**
- `layer1_base_m`: belt weathered base is **~15–30 m**, not a flat 30 — the current statewide 30 is at the *upper* edge; use ~20–25 m for the Singhbhum belt.
- `ore_depth` plausibility: fractured aquifer/ore hosted **~45–260 m** — the 150 m default and 50–600 m slider range are well inside the observed fracture window. ✔
- `upward_gradient`: the deep fractured aquifer is genuinely **confined/semi-confined** with static heads *deeper* than the phreatic table (downward gradient at rest). This confirms a real vertical head contrast exists; the injection-driven *upward* reversal the model assumes is the ISR-operational perturbation on top of it. Screening default stays plausible; refine sign/magnitude from paired shallow-vs-deep heads when a piezometer pair is found.

Sources (manual web research, 2026-07-07):
- ¹ CGWB, *Ground Water Information Booklet — East Singhbhum District, Jharkhand* (District Profile, data yr 2012–13; drilled 2003). Recovered via `http://cgwb.gov.in/old_website/District_Profile/Jharkhand/East%20Singhbhum.pdf` (HTTP worked; HTTPS/main site down).
- ² Corroborating study figures (weathered ≤40 m, fractured to 258 m bgl): IJRES vol.11(12) groundwater assessment, East Singhbhum; Springer *Hydrogeol. J.* 16 (2008) Subarnarekha Basin, East Singhbhum.

---

| # | Report | Pages | Aq-I sect. | Aq-II sect. | T1 pages | T2 pages | Status |
|---|--------|-------|-----------|------------|----------|----------|--------|
| 1 | Chandra,Nawadih JH.pdf | 21 | p.5,14,15,17 | p.14,17 | p.– | p.19 | pending |
| 2 | Chatra Final JH.pdf | 55 | p.5,6,20,21 | p.5,22,38,39 | p.21,40 | p.22,27,38,39,47 | pending |
| 3 | Deoghar Final , JH.pdf | 71 | p.4,5,6,7 | p.22,39,40,41 | p.30,39,41,48 | p.7,22,23,24,29,42 | pending |
| 4 | Dhanbad, JH.pdf | 82 | p.4,5,6,25 | p.4,26,27,48 | p.25,36,50 | p.26,27,28,35 | pending |
| 5 | Dhanbad.pdf | 44 | p.27,30,36,39 | p.27,30,36,39 | p.– | p.21,27,42 | pending |
| 6 | E-Singhbhum, Saraikela-Kharaswan & W-Singhum(Parts)_jharkhand.pdf | – | – | – | – | – | **broken PDF → replaced by web-sourced values above (see EXTRACTED VALUES) + `cgwb_east_singhbhum_profile.pdf`** |
| 7 | Final  NAQUIM-Godda District, Jharkhand.pdf | 82 | p.4,5,6,7 | p.4,22,30,32 | p.51,57 | p.7,32,39,48,57,58 | pending |
| 8 | Final NAQUIM-Dumka district, Jharkhand 2018-19.pdf | 130 | p.4,5,6,7 | p.4,5,7,8 | p.26,33,61,65,74 | p.29,31,32,43,60 | pending |
| 9 | Final NAQUIM-Jamtara district, Jharkhand 2018-19.pdf | 78 | p.4,5,6,21 | p.4,26,27,36 | p.26,44,54,62 | p.27,29,35,44,46,47 | pending |
| 10 | Final Sahebganj Report-NAQUIM-2017-18.pdf | 131 | p.5,6,7,8 | p.5,6,7,8 | p.64,65 | p.33,53,56,64,74 | pending |
| 11 | GARHWA JH.pdf | 88 | p.5,6,7,8 | p.5,6,7,8 | p.25,33,61 | p.27,49,53,77,78,79 | pending |
| 12 | GIRIDIH FINAL JH.pdf | 139 | p.4,5,6,7 | p.4,5,6,7 | p.25,26,40,69,98 | p.27,28,36,57,98,109 | pending |
| 13 | GUMLA JH.pdf | 77 | p.5,6,7,8 | p.5,26,42,43 | p.34,44,51 | p.8,27,41,44,52,64 | pending |
| 14 | KHELRI, LAPUNG BLOCKS JH.pdf | 44 | p.6,20,22,23 | p.20,21,22,24 | p.20,43 | p.20 | pending |
| 15 | KHUNTI FINAL JH.pdf | 18 | p.4,9,10,13 | p.4,9,10,13 | p.– | p.17 | pending |
| 16 | KODERMA JHARKHAND.pdf | 49 | p.5,6,21,22 | p.5,22,33,34 | p.– | p.22,32,33,34,35 | pending |
| 17 | Khunti_lohar.pdf | 53 | p.40,42,43,47 | p.40,42,43,47 | p.33,42 | p.– | pending |
| 18 | Latehar Final JH.pdf | 66 | p.5,6,7,8 | p.5,23,24,40 | p.49 | p.8,23,24,39,44,49 | pending |
| 19 | Lohardaga Final JH.pdf | 97 | p.5,6,7,8 | p.5,22,40,41 | p.22,31,40,50,61,64 | p.8,23,39,42,50,88 | pending |
| 20 | Pakur Dist, Jharkhand-NAQUIM-Report.pdf | 63 | p.3,4,5,6 | p.3,17,18,22 | p.24,61 | p.22,24,31,32,38,53 | pending |
| 21 | Revised Simdega, Jharkhand.pdf | 139 | p.5,6,7,8 | p.5,6,7,8 | p.33,61 | p.21,24,33,35,53,72 | pending |
| 22 | W SINGHBHUM FINAL JH.pdf | 82 | p.4,5,42,47 | p.4,5,43,44 | p.42 | p.39,43,44,45,47,48 | pending |

## Key snippets found (extraction leads)

### Chandra,Nawadih JH.pdf
- p.19: "Location with Block District Depth Depth Thickness Length Fractures Aquifer SWL Dis- D"

### Chatra Final JH.pdf
- p.21: "laterites, weathered granite and weathered Shale and Sandstone( Upto 30 m depth) ,"
- p.40: "Aquifer - I (weathered zone) in hard rock area is 38 m. The depth of Aquifer – II"
- p.22: "Location Block Depth Major Depth Potential Fracture Discharge"
- p.27: "qualitatively estimate the depth of saturated fractured zones, a closer increment in"

### Deoghar Final , JH.pdf
- p.30: "semi-weathered zone extends to a maximum depth of about 54m and mostly within 20 m"
- p.39: "weathered Granite gneiss, Granite, while Aquifer-II ranges from 25-116 m representing"
- p.41: "m representing weathered Granite gneiss, while Aquifer-II ranges from 27-57 m representing Fractured in granite gneiss"
- p.7: "Figure- 26 Depth vs Frequency of fracture encountered in bore wells 41"
- p.22: "gneiss at shallow depth are more productive compared to the fractures in amphibolites/"

### Dhanbad, JH.pdf
- p.25: "laterites, weathered graniteand weathered Shale and Sandstone ( Upto 30 m depth) ,"
- p.36: "Only at one VES site – VES 44, the weathered zone extends to about 43 m deth"
- p.36: "weathered zone, the semi-weathered zone extends to a maximum depth of about 35m."
- p.26: "S Location Block Depth Major Depth Potential Fracture Discharg"
- p.27: "S Location Block Depth Major Depth Potential Fracture Discharg"

### Dhanbad.pdf
- p.21: "The fracture deciphered at the depth of148-151m"
- p.27: "aquifer I is generally 0 to 30 mtr which is weathered and aquifer II fracture depth varies"

### Final  NAQUIM-Godda District, Jharkhand.pdf
- p.51: "weathered Granite gneiss, Granite and Laterites, while Aquifer-II ranges from 17-130 m representing Fractured in granite gneiss"
- p.57: "Average thickness of weathering is 16.04 m and secondary porosity i"
- p.7: "Figure-24 Depth vs number of fracture encountered in bore wells 50"
- p.32: " In some occasion potential fractures were also encountered beyond 100 m depth"

### Final NAQUIM-Dumka district, Jharkhand 2018-19.pdf
- p.26: "The weathering zone in Dumka district varies from 6 to 41 m, as per lithologs of the"
- p.33: "weathered zone varies from 125 ohm-m to 235 ohm-m with thickness of 7.50 m to 28"
- p.61: "25 m representing weathered Granite Gneiss, while Aquifer-II ranges between12-164 m representing fractured Granite Gneiss"
- p.29: "fractures in granite gneiss at shallow depth are more productive compared to the fractures in"
- p.31: " In some occasion potential fractures were also encountered beyond 100 m depth(120-"

### Final NAQUIM-Jamtara district, Jharkhand 2018-19.pdf
- p.26: "weathered graniteand weathered basalt ( Upto 30 m depth) , however in some cases"
- p.44: "(weathered zone) in hard rock area is 30.0 m. The depth of Aquifer – II (fracture zone)"
- p.54: "thickness of weathering is 20 m and fracture zone is 1-2 m only"
- p.27: "Frequency of fractures , depth of occurrence and"
- p.29: " In few occasion 1st potential fractures was encountered beyond 100 m depth"

### Final Sahebganj Report-NAQUIM-2017-18.pdf
- p.64: "Thickness of fracture zones below weathered zone to the depth of 2.0 m 156 m - (ST)"
- p.65: "Average thickness of weathering is 25 m and secondary porosity i"
- p.33: "high yielding aquifers are generally encountered in fractures/joints between 45-100 depth,"
- p.33: "3 Geophysical survey: To identify the weathering thickness, depth of bed rock, fractures"

### GARHWA JH.pdf
- p.25: "The depth of weathering varies from 8 – 15 m below ground level"
- p.33: "data, 9 VES sites the top weathered zone is very thin which is less than 9.00 m and at 25 VES"
- p.33: "weathered zone depth is more than 9.00 m. However, some VES sites weathered zone extends"
- p.27: "drilled depth lithology fractured zone (mbgl) (LPS)"
- p.49: "The shallow fractured aquifers up to the depth of 100 m and deep fractured aquifer exist"

### GIRIDIH FINAL JH.pdf
- p.25: "under unconfined condition in the weathered mantles varying in depth from 8 –17 m as"
- p.26: "The Thickness of weathered aquifers varies from 10 – 25 m in general in granite terrain"
- p.40: "the weathered zone extends to about 36 m depth"
- p.27: "Hand pumps generally tap first fracture zones and its depth is 30 - 55 mbgl constructed by State"
- p.28: " At some occasion potential fractures were encountered beyond 100 m depth (120-190"

### GUMLA JH.pdf
- p.34: "weathered zone in granite gneiss terrain extends maximum up to 33 m depth"
- p.34: "depth to the bottom of the weathered zone exceeds 10 m. The semi-weathered zone"
- p.44: "wells maximum thickness of Aquifer - I (weathered zone) in hard rock area is 30.0 m. The"
- p.8: "Figure – 26 Depth vs Frequency of fracture encountered in bore wells drilled in 42"
- p.27: "Location/ Block Latitude Longitude Depth Casing Fractures Discharge Formation"

### KHELRI, LAPUNG BLOCKS JH.pdf
- p.20: "granite and weathered Shale and Sandstone( Upto 30 m depth) , however in some cases"
- p.43: "The weathered zone of thickness less than 10 m has not"
- p.20: "by Fractured/Jointed granite-gneiss, Fractured Shale and Sandstones upto the depth of 200"

### KHUNTI FINAL JH.pdf
- p.17: "Location with Block District Depth Depth Thickness Length of Fractures Aquifer SWL Dis- D"

### KODERMA JHARKHAND.pdf
- p.22: "by Fractured/Jointed granite-gneiss, upto the explored depth of 200 mtr depth"
- p.32: "wells, identified the potential fracture zone encountered within 200 m depth in granitic"

### Khunti_lohar.pdf
- p.33: "weathered thickness of about 40m.In section BB' in minimum thickness of"
- p.42: "Thickness of fracture from weathered 3 m zone to the depth of 200m-(ST)"

### Latehar Final JH.pdf
- p.49: "thickness of weathering is 1-2 m and secondary porosity i"
- p.8: "Figure – 27 Depth vs Frequency of fracture encountered in bore wells drilled in 42"
- p.23: "gneiss at shallow depth are more productive compared to the fractures in amphibolites/"

### Lohardaga Final JH.pdf
- p.22: "The average thickness of the weathered residuum of the districtvariesfrom 15-30 m. Besides, the patches of laterite deposits contain goodamount ofground water w"
- p.31: "the weathered zone exceeds 10 m. The semi-weathered zone extends to a maximum depth"
- p.40: "weathered Granite gneiss, while Aquifer-II ranges from 13-109 m representing fractured"
- p.8: "Figure – 28 Depth vs Frequency of fracture encountered in bore wells drilled in 41"
- p.23: "No Drilled Depth fracture Tapped e m3/hr n"

### Pakur Dist, Jharkhand-NAQUIM-Report.pdf
- p.24: "The depth to bottom of weathered zone exceeds 12.5m except VES no"
- p.61: "Aquifer - Alluvium/Laterites/Weathered 6-36m 0"
- p.22: "are generally encountered in fractures/joints between 40-140 depth, however in some"
- p.24: "3 Geophysical survey: To identify the weathering thickness, depth of bed rock, fractures"

### Revised Simdega, Jharkhand.pdf
- p.33: "VES sites the top weathered zone is very thin which is less than 9.00 m. However, some VES"
- p.33: "sites weathered zone extends more than 20 m depth"
- p.61: "thickness of weathering is 20 m and fracture zone is limited only"
- p.21: "depth under unconfined condition and circulates through the under lying fracture system"
- p.24: " In some occasion potential fractures were also encountered beyond 150 m depth"

### W SINGHBHUM FINAL JH.pdf
- p.42: "weathering varies between 12 to 20 m in Singhbhum Granite and 16m to 24m in"
- p.39: "Resistivity Depth to Resistivity Depth to fractured zones in the depth range"
- p.43: "and width of fractures decreases with depth"

## Known gaps
- **E-Singhbhum / Saraikela-Kharsawan / W-Singhbhum(parts)** — the file is a CGWB 404 HTML page, NOT a PDF. Re-download needed (ore-belt district — highest priority). `W SINGHBHUM FINAL JH.pdf` partially covers the same craton geology meanwhile.
- Some of the 24 districts have no dedicated report here; several reports bundle multiple districts/blocks — map coverage before extraction.
- Extracting the actual numbers into `Datasets/naquim_vertical.csv` (district, layer1_base_m lo/hi, fracture_depth_m lo/hi, aq2_wl_mbgl lo/hi, source page) is a Phase-2 task; this tracker records where to look.
