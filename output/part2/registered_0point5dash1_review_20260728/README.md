# Registered missing-strut inspection

This conservative run samples a 2-voxel local tube around aligned expected centrelines. Strong missing/disconnected labels are deliberately stricter; intermediate low-support struts are retained as `uncertain_candidate` for CT-neighbourhood review. `strut_candidates.csv` is not ground truth. The STL is intentionally excluded because it is not registered to this CT volume.
