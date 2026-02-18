// Component deduplication helper for demand notes
function addComponentWithMerge(table, comp, qty, person, project, remarks) {
    const partDesc = comp.part_description || comp.part_value || '-';

    // Check if this component already exists in the table
    let foundDuplicate = false;
    const rows = table.getElementsByTagName('tr');

    for (let i = 0; i < rows.length; i++) {
        const row = rows[i];
        const cells = row.cells;

        if (cells.length >= 6) {
            // Get existing values
            const existingPartDesc = cells[1].textContent.trim().split('\n')[0].trim();
            const existingQtyInput = cells[2].querySelector('input[type="number"]');
            const existingProjectInput = cells[4].querySelector('input[type="text"]');
            const existingRemarksInput = cells[5].querySelector('input[type="text"]');

            if (existingQtyInput && existingProjectInput && existingRemarksInput) {
                const existingProject = existingProjectInput.value.trim();
                const existingRemarks = existingRemarksInput.value.trim();

                // Check if part_description, project, and remarks match
                if (existingPartDesc === partDesc &&
                    existingProject === project &&
                    existingRemarks === remarks) {
                    // Merge: add quantities
                    const existingQty = parseInt(existingQtyInput.value);
                    existingQtyInput.value = existingQty + qty;
                    foundDuplicate = true;
                    break;
                }
            }
        }
    }

    return foundDuplicate;
}
