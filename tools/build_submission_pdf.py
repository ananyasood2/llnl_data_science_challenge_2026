from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak, KeepTogether

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'output/final_submission'; OUT.mkdir(parents=True,exist_ok=True)
pdf=OUT/'Lattice_CT_Inspection_Final_Submission.pdf'
styles=getSampleStyleSheet()
styles.add(ParagraphStyle('TitleX',parent=styles['Title'],fontName='Helvetica-Bold',fontSize=23,leading=28,textColor=colors.HexColor('#1F4D78'),alignment=TA_CENTER,spaceAfter=12))
styles.add(ParagraphStyle('SubX',parent=styles['Normal'],fontSize=12,leading=16,textColor=colors.HexColor('#505050'),alignment=TA_CENTER,spaceAfter=20))
styles.add(ParagraphStyle('H1X',parent=styles['Heading1'],fontName='Helvetica-Bold',fontSize=16,leading=20,textColor=colors.HexColor('#2E74B5'),spaceBefore=14,spaceAfter=7))
styles.add(ParagraphStyle('BodyX',parent=styles['BodyText'],fontName='Helvetica',fontSize=9.4,leading=13,spaceAfter=6))
styles.add(ParagraphStyle('CapX',parent=styles['BodyText'],fontName='Helvetica-Oblique',fontSize=8,leading=10,textColor=colors.HexColor('#505050'),alignment=TA_CENTER,spaceAfter=9))
S=[]
def P(t, style='BodyX'): S.append(Paragraph(t,styles[style]))
def H(t): S.append(Paragraph(t,styles['H1X']))
def T(headers, rows, widths):
 d=[headers]+rows; tab=Table(d,colWidths=[w*inch for w in widths],repeatRows=1,hAlign='CENTER')
 tab.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#E8EEF5')),('GRID',(0,0),(-1,-1),0.35,colors.HexColor('#AAB5C2')),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTNAME',(0,1),(-1,-1),'Helvetica'),('FONTSIZE',(0,0),(-1,-1),8),('LEADING',(0,0),(-1,-1),10),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)])); S.append(tab); S.append(Spacer(1,8))
def F(rel,caption,w=5.9):
 p=ROOT/rel
 if p.exists(): S.append(KeepTogether([Image(str(p),width=w*inch,height=w*inch*(p.stat().st_size and 0.58)),Paragraph(caption,styles['CapX'])]))

P('Lattice CT Inspection<br/>Final Technical Submission','TitleX'); P('Part 1: Unit-cell segmentation and NDE<br/>Part 2: Registered 0.5%-missing octet-lattice screening','SubX')
T(['Submission scope','Status'],[['Part 1','Completed: segmentation, skeleton, and NDE visual report'],['Part 2','Completed: registered CT/graph candidate screening and sensitivity analysis'],['Quantitative confirmation','Not supported by available evidence; no missing struts confirmed']],[2.1,4.3])
P('Prepared from the repository saved, traceable analysis artifacts. Unregistered STL files were excluded from quantitative CT comparisons.')
S.append(PageBreak())
H('Executive Summary')
P('This submission consolidates the completed Part 1 and Part 2 outputs. Part 1 establishes a reproducible segmentation-to-NDE workflow on the unit-cell CT volume. Part 2 evaluates the supplied registered 0.5%-missing octet-lattice CT/JSON pair using a distance-tolerant centerline tube test and sensitivity checks.')
T(['Finding','Result','Interpretation'],[['Part 1 selected threshold','0.005813','Otsu-selected balance of continuity and compactness.'],['Part 1 mask','717,852 voxels (4.2787%)','Selected mask for 256 x 256 x 256 volume.'],['Part 1 skeleton','3,182 voxels; 1 component','Connected structural proxy.'],['Part 2 design graph','18,468 struts; 10,206 junctions','Supplied registered JSON only.'],['Part 2 retained setting','Tube radius 2; threshold 39,725','Least flagging tested radius.'],['Part 2 confirmation','0 confirmed missing struts','Candidates are not physical defect labels.']],[1.65,1.65,3.0])
H('1. Objectives and Data')
P('The work has two objectives: (1) produce a traceable segmentation, skeletonization, and NDE workflow for the unit-cell volume; and (2) screen an aligned octet-lattice specimen for missing or disconnected strut candidates using only the supplied registered CT graph.')
T(['Dataset','Input','Use'],[['Part 1 unit cell','data/unitcell/unitcell.npy','Segmentation and NDE.'],['Part 2 CT','0.5%-missing TIFF, 761 x 815 x 837 uint16','As-built image evidence.'],['Part 2 design','Registered JSON, 18,468 struts','Expected centerlines in CT coordinates.'],['STL variants','Unregistered','Excluded from quantitative comparison.']],[1.25,2.6,2.55])
H('2. Part 1 Methods and Results')
P('Three thresholds were compared. The selected threshold, 0.005813, is the Otsu value and provided a balanced foreground fraction with visually continuous lattice material. The chosen mask was skeletonized and rendered from two 3D perspectives for NDE review.')
T(['Threshold','Foreground fraction','Decision'],[['0.004500','4.3416%','Lower candidate.'],['0.005813','4.2787%','Selected Otsu threshold.'],['0.007000','4.2480%','Higher candidate.']],[1.6,1.8,3.0])
F('output/part1/unitcell_raw_slice_128.png','Figure 1. Part 1 unit-cell raw CT slice (slice 128).',4.4)
F('output/part1/unitcell_mask_slice_128.png','Figure 2. Part 1 selected segmentation mask at the same slice.',4.4)
S.append(PageBreak())
H('Part 1 NDE Visual Validation')
F('output/part1/nde_report/view_a.png','Figure 3. NDE View A: elevation 30 degrees, azimuth 45 degrees.',5.2)
F('output/part1/nde_report/view_b.png','Figure 4. NDE View B: elevation 60 degrees, azimuth 45 degrees.',5.2)
P('Part 1 conclusion: the selected mask and skeleton are dimensionally compatible with the source volume. The single connected skeletal component supports intended unit-cell connectivity; it is not a mechanical simulation.')
S.append(PageBreak())
H('3. Part 2 Registered CT-to-Graph Screening')
P('The Part 2 graph was supplied in CT voxel coordinates. Expected strut centerlines were sampled after XYZ-to-CT indexing conversion. A local tube test used the 75th-percentile CT intensity around each sample, which is more tolerant of small offsets than a single centerline voxel. Samples were trimmed to the central 8%-92% of each strut to reduce junction influence.')
T(['Parameter','Retained value','Reason'],[['Tube radius','2 CT voxels','Least flagging among radii 1, 2, and 3.'],['Threshold','39,725','Separation criterion retaining median support >= 0.60.'],['Low support rule','Material fraction < 0.04','Conservative candidate screen.'],['Disconnected rule','Fraction < 0.35 with long gap','Separates gap-like behavior.']],[1.45,1.65,3.3])
H('4. Part 2 Sensitivity and Candidate Results')
F('output/part2/refined_registration_20260728/tube_r2/threshold_diagnostics.png','Figure 5. Radius-2 centerline intensity distribution and threshold-candidate separation.',6.1)
T(['Tube radius','Threshold','Low support','Disconnected','Uncertain','Clear'],[['1','39,725','1,217','5,614','1,199','10,438'],['2 retained','39,725','1,049','5,262','1,083','11,074'],['3','42,017','1,159','6,505','1,384','9,420']],[0.85,0.95,1.1,1.1,1.0,1.05])
P('At the retained radius-2 setting, 7,394 struts are review candidates: 1,049 low-support, 5,262 disconnected, and 1,083 uncertain. This is a screen, not a defect count. Dependence on tube radius and threshold is stronger evidence for residual registration, segmentation, and partial-volume effects than for thousands of physical defects.')
F('output/part2/registered_screen_20260728/ct_mask_evidence_overlay.png','Figure 6. Supplemental CT/segmentation overlay. Supporting visual evidence only; not the authoritative result source.',6.1)
H('5. Discussion, Limitations, and Recommendation')
P('The nominal 0.5% label implies approximately 92 intentionally removed struts but was never used as a classification target. The screen returns far more candidates than the nominal label and does so inconsistently as parameters change. A valid report retains this discrepancy rather than tuning the result to meet the expectation.')
P('The supplied JSON does not contain transform covariance, independent fiducials, or per-strut ground truth. Therefore an additional rigid or deformable registration refinement cannot be defensibly estimated from the available artifacts. The appropriate conclusion is zero confirmed physical missing struts, with a ranked candidate list for review.')
T(['Claim','Status','Evidence'],[['Registered JSON and CT used','Supported','Paths and dimensions recorded in summaries.'],['Unregistered STL excluded','Supported','Workflow and provenance state this explicitly.'],['Candidates reproducible','Supported','CSV and diagnostics saved.'],['Physical defect count known','Not supported','No truth join or blinded review.'],['Mechanical repair benefit known','Not supported','Historical repair output is non-FEA only.']],[2.15,1.1,2.95])
H('6. Recommended Next Steps')
P('1. Obtain independent registration landmarks or transform uncertainty.  2. Perform blinded CT-neighborhood adjudication of ranked candidates.  3. Calculate precision, recall, F1, and a confusion matrix if registered truth becomes available.  4. Reuse radius-1/radius-2/radius-3 outputs as a future registration-improvement baseline.')
S.append(PageBreak())
H('Appendix A. Deliverable Manifest')
T(['Part','Artifact group','Contents'],[['1','threshold_optimizer/','Three masks, slice comparisons, and selection memo.'],['1','unitcell_mask.npy; unitcell_skeleton.npy','Selected segmentation and skeleton arrays.'],['1','nde_report/','NDE report and two 3D renders.'],['1','registered_strut_screen/','Registered strut screen CSV and JSON.'],['2','metadata/; graph_comparison/','Dataset inventory and graph artifacts.'],['2','refined_registration_20260728/','Authoritative sensitivity readout and radius runs.'],['2','tube_r2/strut_candidates.csv','All 18,468 records for retained setting.'],['2','registered_screen_20260728/','Supplemental overlay, provenance, sensitivity, interactive scene.'],['2','visual_repair*/','Historical non-FEA candidate-repair scenarios.']],[0.55,2.2,3.5])
H('Appendix B. Reproducibility')
P('Part 1 source: data/unitcell/unitcell.npy. Part 2 CT: data/missing_struts/tif_stacks/210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.tif. Part 2 design: data/missing_struts/registered_jsons/210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json. Authoritative output: output/part2/refined_registration_20260728/tube_r2/. Complete artifact listing: output/DELIVERABLES.md.')
def footer(c,doc):
 c.saveState(); c.setFont('Helvetica',8); c.setFillColor(colors.HexColor('#505050')); c.drawString(.85*inch,.45*inch,'LLNL DSSI 2026 | Lattice CT Inspection Submission'); c.drawRightString(7.65*inch,.45*inch,f'Page {doc.page}'); c.restoreState()
SimpleDocTemplate(str(pdf),pagesize=letter,rightMargin=.85*inch,leftMargin=.85*inch,topMargin=.78*inch,bottomMargin=.7*inch).build(S,onFirstPage=footer,onLaterPages=footer)
print(pdf)
