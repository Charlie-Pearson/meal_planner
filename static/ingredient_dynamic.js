document.addEventListener('DOMContentLoaded', function() {
    const ingredientsList = document.getElementById('ingredients-list');
    const addIngredientBtn = document.getElementById('add-ingredient-btn');
    const newIngredientBtn = document.getElementById('new-ingredient-btn-edit');
    const newIngredientModal = new bootstrap.Modal(document.getElementById('ingredientModalEdit'));
    
    // Initialize the form with existing ingredients
    if (window.formIngredients && window.formIngredients.length > 0) {
        window.formIngredients.forEach(ing => {
            addIngredientRow(ing);
        });
    } else {
        // Add an empty row if no ingredients
        addIngredientRow();
    }

    // Add existing ingredient
    addIngredientBtn.addEventListener('click', function() {
        addIngredientRow();
    });

    // Open new ingredient modal
    newIngredientBtn.addEventListener('click', function() {
        document.getElementById('new-ingredient-name').value = '';
        document.getElementById('new-ingredient-unit').value = '';
        newIngredientModal.show();
    });

    // Save new ingredient
    document.getElementById('save-new-ingredient').addEventListener('click', function() {
        const name = document.getElementById('new-ingredient-name').value.trim();
        const unit = document.getElementById('new-ingredient-unit').value.trim();
        
        if (!name) {
            alert('Please enter an ingredient name');
            return;
        }
        
        // Add the new ingredient to the list
        addIngredientRow({
            id: '',
            name: name,
            quantity: '',
            unit: unit,
            aisle: ''
        });
        
        // Close the modal and reset the form
        newIngredientModal.hide();
    });

    // Handle ingredient selection
    function onIngredientSelect(select) {
        const row = select.closest('.ingredient-row');
        const selectedOption = select.options[select.selectedIndex];
        
        if (selectedOption.value) {
            const ingredient = window.allIngredients.find(i => i.id.toString() === selectedOption.value);
            if (ingredient) {
                row.querySelector('.ingredient-quantity').value = '';
                row.querySelector('.ingredient-unit').value = ingredient.unit || '';
                row.querySelector('.ingredient-aisle').value = ingredient.aisle || '';
                row.querySelector('.ingredient-name').value = ingredient.name;
                row.querySelector('.ingredient-id').value = ingredient.id;
            }
        }
    }

    // Add a new ingredient row
    function addIngredientRow(ingredient = {}) {
        const row = document.createElement('div');
        row.className = 'ingredient-row mb-2';
        
        // Create a unique ID for this row
        const rowId = 'ingredient-' + Math.random().toString(36).substr(2, 9);
        
        // Create the HTML for the row
        row.innerHTML = `
            <div class="row g-2 align-items-center">
                <div class="col-md-4">
                    <input type="text" 
                           class="form-control ingredient-name" 
                           name="ingredient_names[]" 
                           value="${ingredient.name || ''}" 
                           placeholder="Ingredient name" 
                           required>
                    <input type="hidden" class="ingredient-id" name="ingredient_ids[]" value="${ingredient.id || ''}">
                </div>
                <div class="col-md-2">
                    <input type="number" 
                           class="form-control ingredient-quantity" 
                           name="ingredient_quantities[]" 
                           value="${ingredient.quantity || ''}" 
                           placeholder="Qty" 
                           step="0.01" 
                           min="0" 
                           required>
                </div>
                <div class="col-md-2">
                    <input type="text" 
                           class="form-control ingredient-unit" 
                           name="ingredient_units[]" 
                           value="${ingredient.unit || ''}" 
                           placeholder="Unit">
                </div>
                <div class="col-md-3">
                    <input type="text" 
                           class="form-control ingredient-aisle" 
                           name="ingredient_aisles[]" 
                           value="${ingredient.aisle || ''}" 
                           placeholder="Aisle" 
                           list="aisle-suggestions">
                </div>
                <div class="col-md-1">
                    <button type="button" class="btn btn-danger btn-sm remove-ingredient" title="Remove">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            </div>
        `;
        
        // Add event listener for the remove button
        const removeBtn = row.querySelector('.remove-ingredient');
        removeBtn.addEventListener('click', function() {
            row.remove();
        });
        
        // Add the row to the list
        ingredientsList.appendChild(row);
        
        // Initialize autocomplete for the new row
        const nameInput = row.querySelector('.ingredient-name');
        if (nameInput) {
            initializeAutocomplete(nameInput);
        }
    }
    
    // Initialize autocomplete for ingredient names
    function initializeAutocomplete(input) {
        $(input).autocomplete({
            source: function(request, response) {
                const term = request.term.toLowerCase();
                const matches = window.allIngredients.filter(ing => 
                    ing.name.toLowerCase().includes(term)
                );
                response(matches);
            },
            minLength: 2,
            select: function(event, ui) {
                if (ui.item) {
                    const row = $(this).closest('.ingredient-row');
                    row.find('.ingredient-id').val(ui.item.id);
                    row.find('.ingredient-unit').val(ui.item.unit || '');
                    row.find('.ingredient-aisle').val(ui.item.aisle || '');
                }
                return false;
            }
        }).data('ui-autocomplete')._renderItem = function(ul, item) {
            return $("<li>")
                .append(`<div>${item.name} <small class="text-muted">${item.unit || 'unit'}</small></div>`)
                .appendTo(ul);
        };
    }
    
    // Initialize autocomplete for existing inputs
    document.querySelectorAll('.ingredient-name').forEach(input => {
        initializeAutocomplete(input);
    });
});
