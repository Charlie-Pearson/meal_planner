// Initialize variables for ingredient management
let allIngredients = [];
let distinctAisles = [];

// Function to initialize Select2 for an element
function initSelect2($element) {
    // Convert allIngredients to the format expected by Select2
    const select2Data = allIngredients.map(ing => ({
        id: ing.id,
        text: ing.name,
        unit: ing.unit || '',
        aisle: ing.aisle || ''
    }));
    
    $element.select2({
        placeholder: 'Select an ingredient',
        width: '100%',
        allowClear: true,
        data: select2Data,
        dropdownParent: $element.parent()
    });
    
    // Handle selection change to update unit and aisle fields
    $element.on('select2:select', function(e) {
        const data = e.params.data;
        const $row = $(this).closest('.ingredient-row');
        $row.find('.ingredient-unit').val(data.unit || '');
        $row.find('.ingredient-aisle').val(data.aisle || '');
    });
}

// Function to create a new ingredient row
function createIngredientRow(index) {
    const rowId = `ingredient-row-${index}`;
    const rowHtml = `
        <div class="ingredient-row row g-2 mb-2" id="${rowId}">
            <div class="col-md-5">
                <select class="form-select ingredient-select" name="ingredients[${index}][ingredient_id]" required>
                    <option value="">Select an ingredient</option>
                </select>
            </div>
            <div class="col-md-2">
                <input type="number" class="form-control" name="ingredients[${index}][quantity]" 
                    step="0.01" min="0" placeholder="Qty" required>
            </div>
            <div class="col-md-2">
                <input type="text" class="form-control ingredient-unit" 
                    name="ingredients[${index}][unit]" placeholder="Unit" readonly>
            </div>
            <div class="col-md-2">
                <input type="text" class="form-control ingredient-aisle" 
                    name="ingredients[${index}][aisle]" placeholder="Aisle" readonly>
            </div>
            <div class="col-md-1">
                <button type="button" class="btn btn-outline-danger remove-ingredient" title="Remove">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        </div>`;
    
    return rowHtml;
}

// Function to add a new ingredient row
function addIngredientRow() {
    const $ingredientsList = $('#ingredients-list');
    const newIndex = $('.ingredient-row').length;
    
    // Create and append the new row
    const newRow = createIngredientRow(newIndex);
    $ingredientsList.append(newRow);
    
    // Initialize Select2 for the new row
    const $newSelect = $ingredientsList.find(`#ingredient-row-${newIndex} .ingredient-select`);
    initSelect2($newSelect);
    
    console.log('Added new ingredient row');
}

// Function to handle ingredient row removal
function handleRemoveIngredient() {
    $(this).closest('.ingredient-row').remove();
    // Renumber remaining rows
    $('.ingredient-row').each(function(index) {
        $(this).find('[name]').each(function() {
            const name = $(this).attr('name').replace(/\[\d+\]/, `[${index}]`);
            $(this).attr('name', name);
        });
    });
}

// Function to initialize the recipe form
function initializeRecipeForm(ingredientsData, aisles) {
    console.log('Initializing recipe form...');
    
    // Set global variables
    allIngredients = ingredientsData || [];
    distinctAisles = aisles || [];
    
    console.log('Ingredients data:', allIngredients);
    console.log('Distinct aisles:', distinctAisles);
    
    // Remove any existing event handlers to prevent duplicates
    $(document).off('click', '#add-ingredient-btn');
    $(document).off('click', '#new-ingredient-btn-edit');
    
    // Handle add ingredient button click
    $(document).on('click', '#add-ingredient-btn', function(e) {
        e.preventDefault();
        console.log('Add ingredient button clicked');
        addIngredientRow();
        return false;
    });
    
    // Handle new ingredient button click
    $(document).on('click', '#new-ingredient-btn-edit', function(e) {
        e.preventDefault();
        console.log('New ingredient button clicked');
        // Clear the modal form
        $('#new-ingredient-name').val('');
        $('#new-ingredient-unit').val('');
        $('#new-ingredient-aisle').val('');
        // Show the modal
        const modal = new bootstrap.Modal(document.getElementById('ingredientModalEdit'));
        modal.show();
        return false;
    });
    
    // Handle remove ingredient button clicks
    $(document).on('click', '.remove-ingredient', handleRemoveIngredient);
    
    // Handle ingredient selection change
    $(document).on('change', '.ingredient-select', function() {
        console.log('Ingredient selection changed');
        const $row = $(this).closest('.ingredient-row');
        const selectedId = $(this).val();
        const ingredient = allIngredients.find(ing => ing.id == selectedId);
        
        if (ingredient) {
            console.log('Selected ingredient:', ingredient);
            $row.find('.ingredient-unit')
                .val(ingredient.unit)
                .prop('readonly', true);
            $row.find('.ingredient-aisle')
                .val(ingredient.aisle)
                .prop('readonly', true);
        } else {
            console.log('No ingredient selected');
            $row.find('.ingredient-unit')
                .val('')
                .prop('readonly', true);
            $row.find('.ingredient-aisle')
                .val('')
                .prop('readonly', true);
        }
    });
    
    // Remove autocomplete from all aisle inputs and ensure they are read-only
    $('.ingredient-aisle').autocomplete('destroy').prop('readonly', true);
    
    // Handle save new ingredient
    $('#save-new-ingredient').off('click').on('click', function() {
        const name = $('#new-ingredient-name').val().trim();
        const unit = $('#new-ingredient-unit').val().trim();
        const aisle = $('#new-ingredient-aisle').val().trim();
        
        console.log('Saving new ingredient:', { name, unit, aisle });
        
        if (!name || !unit || !aisle) {
            alert('Please fill in all fields');
            return;
        }
        
        // Get CSRF token from the form
        const csrfToken = $('input[name="csrf_token"]').val();
        
        // Send AJAX request to add new ingredient
        $.ajax({
            url: '/api/ingredients',
            method: 'POST',
            contentType: 'application/json',
            headers: {
                'X-CSRFToken': csrfToken
            },
            data: JSON.stringify({
                name: name,
                unit: unit,
                aisle: aisle
            }),
            success: function(response) {
                console.log('New ingredient saved:', response);
                if (response.success) {
                    // Add new ingredient to the list and update dropdowns
                    const newIngredient = {
                        id: response.ingredient.id,
                        name: name,
                        unit: unit,
                        aisle: aisle
                    };
                    
                    allIngredients.push(newIngredient);
                    
                    if (!distinctAisles.includes(aisle)) {
                        distinctAisles.push(aisle);
                    }
                    
                    // Close the modal
                    $('#ingredientModalEdit').modal('hide');
                    
                    // Add the new ingredient to the form
                    addIngredientRow();
                    
                    // Update the last added row with the new ingredient
                    const $lastRow = $('.ingredient-row').last();
                    $lastRow.find('.ingredient-select').val(newIngredient.id).trigger('change');
                    
                    // Show success message
                    alert('Ingredient added successfully!');
                } else {
                    alert('Failed to add ingredient: ' + (response.message || 'Unknown error'));
                }
            },
            error: function(xhr, status, error) {
                console.error('Error saving ingredient:', error);
                alert('Error saving ingredient: ' + (xhr.responseJSON?.message || 'Unknown error'));
            }
        });
    });
    
    // Handle remove ingredient button
    $(document).on('click', '.remove-ingredient', function() {
        const $row = $(this).closest('.ingredient-row');
        if ($('.ingredient-row').length > 1) {
            $row.remove();
            console.log('Removed ingredient row');
        } else {
            // If it's the last row, just clear the values
            $row.find('input').val('');
            $row.find('select').val('').trigger('change');
            console.log('Cleared last ingredient row');
        }
    });
    
    console.log('Recipe form initialization complete');
}

// Initialize the modal focus when shown
$('#ingredientModalEdit').on('shown.bs.modal', function() {
    $('#new-ingredient-name').focus();
});

// Handle form submission
$('#recipe-form').on('submit', function(e) {
    e.preventDefault();
    
    // Collect all form data
    const formData = new FormData(this);
    
    // Add ingredients data
    $('.ingredient-row').each(function(index) {
        const $row = $(this);
        const ingredientId = $row.find('.ingredient-select').val();
        const quantity = $row.find('input[name$="[quantity]"').val();
        const unit = $row.find('.ingredient-unit').val();
        const aisle = $row.find('.ingredient-aisle').val();
        const name = $row.find('.ingredient-select option:selected').text();
        
        // Only add if we have a selected ingredient and quantity
        if (ingredientId && quantity) {
            formData.append(`ingredient_ids[]`, ingredientId);
            formData.append(`ingredient_quantities[]`, quantity);
            formData.append(`ingredient_units[]`, unit || '');
            formData.append(`ingredient_aisles[]`, aisle || '');
            formData.append(`ingredient_names[]`, name);
        }
    });
    
    // Submit the form with all data
    $.ajax({
        url: $(this).attr('action'),
        method: 'POST',
        data: formData,
        processData: false,
        contentType: false,
        success: function(response) {
            if (response.redirect) {
                window.location.href = response.redirect;
            } else {
                // Handle success (e.g., show success message)
                alert('Recipe saved successfully!');
                window.location.href = '/';
            }
        },
        error: function(xhr) {
            // Handle error (e.g., show error message)
            const errorMsg = xhr.responseJSON?.message || 'Failed to save recipe';
            alert('Error: ' + errorMsg);
            console.error('Error saving recipe:', xhr.responseJSON || xhr.responseText);
        }
    });
});
