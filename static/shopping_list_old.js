// JavaScript logic from the old shopping_list.html for check/uncheck and re-add items
// This is extracted for future reference or reintegration

function handleItemCheck(checkbox) {
    const listItem = checkbox.closest('li');
    const normName = listItem.dataset.normName;
    const isChecked = checkbox.checked; // true = move TO removed

    // Gather item data FROM data attributes for sending and potential re-creation
    const itemDataForStorage = {
        name: listItem.dataset.name, normalized_name: normName, aisle: listItem.dataset.aisle,
        display_quantity: listItem.dataset.displayQuantity, unit: listItem.dataset.unit,
        is_custom: listItem.hasAttribute('data-is-custom'),
        custom_item_index: listItem.dataset.customIndex
    };

    fetch('/move_shopping_item', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ norm_name: normName, isChecked: isChecked, item_data: itemDataForStorage })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            moveItemVisually(listItem, isChecked, data.removed_item_data || itemDataForStorage);
        } else { checkbox.checked = !isChecked; alert("Error: " + (data.error || "Could not update item.")); }
    })
    .catch(error => { checkbox.checked = !isChecked; console.error('Error:', error); alert("Network Error."); })
    .finally(() => { if (document.getElementById(checkbox.id)) { document.getElementById(checkbox.id).disabled = false; } });
}

function handleReAddItem(button) {
    const normName = button.value;
    fetch('/move_shopping_item', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ norm_name: normName, isChecked: false })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            addItemBackToVisualList(data.item_data);
        } else { alert("Error: " + (data.error || "Could not re-add item.")); }
    })
    .catch(error => { console.error('Error:', error); alert("Network Error."); });
}

// ... (other helper functions from old template, e.g., moveItemVisually, addItemBackToVisualList, etc.)
// See old shopping_list.html for full logic
