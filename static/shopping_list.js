// shopping_list.js
// Handles live updates for checking/unchecking shopping list items

document.addEventListener('DOMContentLoaded', function() {
    // Get CSRF token from meta tag
    const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
    
    // Initialize Socket.IO
    const socket = io();
    
    // Join shopping list room when page loads
    socket.emit('join_shopping_list');
    
    // Handle item updates from other users
    socket.on('item_updated', function(data) {
        const checkbox = document.querySelector(`#item-${data.item_id}`);
        const label = document.querySelector(`label[for="item-${data.item_id}"]`);
        
        if (checkbox && !checkbox.isUpdating && checkbox.checked !== data.is_checked) {
            console.log('Received update for item:', data);
            checkbox.checked = data.is_checked;
            
            if (label) {
                if (data.is_checked) {
                    label.classList.add('text-muted', 'text-decoration-line-through');
                } else {
                    label.classList.remove('text-muted', 'text-decoration-line-through');
                }
            }
        }
    });
    
    // Handle disconnections
    socket.on('disconnect', () => {
        console.warn('WebSocket disconnected. Updates may be delayed.');
    });
    
    // Handle reconnections
    socket.on('connect', () => {
        console.log('WebSocket reconnected. Rejoining shopping list room...');
        socket.emit('join_shopping_list');
    });
    
    // Add event listeners to all checkboxes
    document.querySelectorAll('.item-checkbox').forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            const itemId = this.getAttribute('data-item-id');
            const isChecked = this.checked;
            const label = document.querySelector(`label[for="item-${itemId}"]`);
            
            // Set a flag to prevent this checkbox from being updated by WebSocket
            this.isUpdating = true;
            
            // Debug logging
            console.log('Updating item:', {
                itemId: itemId,
                isChecked: isChecked
            });
            
            // Optimistically update UI
            if (label) {
                if (isChecked) {
                    label.classList.add('text-muted', 'text-decoration-line-through');
                } else {
                    label.classList.remove('text-muted', 'text-decoration-line-through');
                }
            }
            
            // Send update to server
            fetch('/update-shopping-item-checked', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({
                    item_id: itemId,
                    is_checked: isChecked
                })
            })
            .then(response => response.json().then(data => ({ ok: response.ok, status: response.status, data: data })))
            .then(({ ok, status, data }) => {
                // Clear the update flag regardless of success/failure
                this.isUpdating = false;
                
                if (!ok) {
                    // Revert UI changes
                    if (label) {
                        if (!isChecked) {
                            label.classList.add('text-muted', 'text-decoration-line-through');
                        } else {
                            label.classList.remove('text-muted', 'text-decoration-line-through');
                        }
                    }
                    this.checked = !isChecked;
                    
                    // Show appropriate error message
                    if (status === 404) {
                        throw new Error('Item not found');
                    } else if (status === 403) {
                        throw new Error('Not authorized to update this item');
                    } else if (status === 400) {
                        throw new Error(data.error || 'Invalid request');
                    } else {
                        throw new Error(data.error || 'Failed to update item');
                    }
                }
                
                if (!data.success) {
                    throw new Error(data.error || 'Update failed');
                }
                
                console.log('Updated successfully:', data);
            })
            .catch(error => {
                console.error('Error:', error);
                alert(error.message || 'Failed to update item');
                // Clear the update flag on error
                this.isUpdating = false;
            });
        });
    });
    
    // Cleanup when page is closed/navigated away
    window.addEventListener('beforeunload', function() {
        socket.emit('leave_shopping_list');
    });
});

function showShoppingListMessage(msg) {
    let msgDiv = document.getElementById('shopping-list-msg');
    if (!msgDiv) {
        msgDiv = document.createElement('div');
        msgDiv.id = 'shopping-list-msg';
        msgDiv.style.position = 'fixed';
        msgDiv.style.bottom = '30px';
        msgDiv.style.left = '50%';
        msgDiv.style.transform = 'translateX(-50%)';
        msgDiv.style.background = '#28a745';
        msgDiv.style.color = 'white';
        msgDiv.style.padding = '10px 20px';
        msgDiv.style.borderRadius = '5px';
        msgDiv.style.boxShadow = '0 2px 8px rgba(0,0,0,0.2)';
        msgDiv.style.zIndex = 10000;
        document.body.appendChild(msgDiv);
    }
    msgDiv.textContent = msg;
    msgDiv.style.display = 'block';
    clearTimeout(msgDiv._timeout);
    msgDiv._timeout = setTimeout(() => {
        msgDiv.style.display = 'none';
    }, 2000);
}

function updateCheckedStatus(itemId, isChecked, checkboxElem) {
    // Show initial alert with the values being sent
    alert(`Sending to database:\nItem ID: ${itemId}\nRequested status: ${isChecked}`);

    fetch('/update-shopping-item-checked', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
        },
        body: JSON.stringify({ item_id: itemId, is_checked: isChecked })
    })
    .then(response => {
        if (!response.ok) {
            // Server returned an error status
            return response.json().then(errorData => {
                throw new Error(errorData.error || 'Server returned ' + response.status);
            });
        }
        return response.json();
    })
    .then(data => {
        if (data.success) {
            // Show detailed confirmation alert
            alert(
                'Database Update Confirmation:\n' +
                '-------------------------\n' +
                `Item ID: ${data.item_id}\n` +
                `Previous status: ${data.old_status ? 'checked' : 'unchecked'}\n` +
                `Requested status: ${data.requested_status ? 'checked' : 'unchecked'}\n` +
                `Final status in DB: ${data.actual_status ? 'checked' : 'unchecked'}\n` +
                '-------------------------\n' +
                data.message
            );
            
            // Update UI based on actual database state
            const itemDiv = document.querySelector('.list-group-item');
            const label = itemDiv ? itemDiv.querySelector('label') : null;
            if (label) {
                if (data.actual_status) {
                    label.classList.add('text-muted', 'text-decoration-line-through');
                } else {
                    label.classList.remove('text-muted', 'text-decoration-line-through');
                }
                // Ensure checkbox matches database state
                if (checkboxElem) {
                    checkboxElem.checked = data.actual_status;
                }
            }
        } else {
            throw new Error(data.error || 'Unknown error');
        }
    })
    .catch(error => {
        // Show error alert and revert UI
        alert('Error: ' + error.message);
        if (checkboxElem) {
            checkboxElem.checked = !isChecked; // Revert checkbox
        }
        const itemDiv = document.querySelector('.list-group-item');
        const label = itemDiv ? itemDiv.querySelector('label') : null;
        if (label) {
            // Revert label style to previous state
            if (!isChecked) {
                label.classList.add('text-muted', 'text-decoration-line-through');
            } else {
                label.classList.remove('text-muted', 'text-decoration-line-through');
            }
        }
    });
}
