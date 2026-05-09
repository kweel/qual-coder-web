document.addEventListener('DOMContentLoaded', function() {
    // Load existing codes for all comments
    document.querySelectorAll('.codes-list').forEach(codesList => {
        const commentId = codesList.dataset.commentId;
        loadExistingCodes(commentId, codesList);
    });

    // Handle save code button clicks
    document.querySelectorAll('.save-code-btn').forEach(button => {
        button.addEventListener('click', function() {
            const commentId = this.dataset.commentId;
            const codeInput = this.parentElement.querySelector('input');
            const codesList = this.closest('.coding-form').querySelector('.codes-list');
            const code = codeInput.value.trim();
            
            if (!code) return;
            
            fetch('/save_code', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    comment_id: commentId,
                    code: code
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    codeInput.value = '';
                    button.classList.add('btn-success');
                    button.textContent = 'Saved!';
                    setTimeout(() => {
                        button.classList.remove('btn-success');
                        button.textContent = 'Save';
                    }, 2000);
                    // Reload codes after saving
                    loadExistingCodes(commentId, codesList);
                }
            });
        });
    });

    const themeToggle = document.getElementById('theme-toggle');
    const body = document.body;
    const icon = themeToggle.querySelector('i');
    const text = themeToggle.querySelector('span');
    
    // Check for saved theme preference
    const currentTheme = localStorage.getItem('theme');
    if (currentTheme) {
        body.classList.add(currentTheme);
        if (currentTheme === 'dark-mode') {
            icon.classList.replace('fa-moon', 'fa-sun');
            text.textContent = 'Light Mode';
            
        }
    }
    
    // Add theme toggle event listener
    themeToggle.addEventListener('click', function() {
        body.classList.toggle('dark-mode');
        
        // Update the toggle button
        if (body.classList.contains('dark-mode')) {
            icon.classList.replace('fa-moon', 'fa-sun');
            text.textContent = 'Light Mode';
            localStorage.setItem('theme', 'dark-mode');
        } else {
            icon.classList.replace('fa-sun', 'fa-moon');
            text.textContent = 'Dark Mode';
            localStorage.setItem('theme', '');
        }
    });
    
    // document.getElementById('export-codes')?.addEventListener('click', function() {
    //     window.location.href = '/export_codes';
    // });
});

function loadExistingCodes(commentId, codesList) {
    fetch(`/get_codes/${commentId}`)
        .then(response => response.json())
        .then(data => {
            codesList.innerHTML = data.codes
                .map(code => `
                    <li class="d-flex justify-content-between align-items-center mb-1">
                        <span>${code.code} <small class="text-muted">(${code.created_at})</small></span>
                        <button class="btn btn-danger btn-sm delete-code-btn" 
                                data-code-id="${code.id}" 
                                data-comment-id="${commentId}">
                            ×
                        </button>
                    </li>
                `).join('');
            
            // Add delete handlers
            codesList.querySelectorAll('.delete-code-btn').forEach(button => {
                button.addEventListener('click', function() {
                    const codeId = this.dataset.codeId;
                    if (confirm('Are you sure you want to delete this code?')) {
                        deleteCode(codeId, commentId, codesList);
                    }
                });
            });
            
            // Highlight comment if it has codes
            const commentCard = document.querySelector(`.comment[data-comment-id="${commentId}"]`);
            if (commentCard) {
                if (data.codes.length > 0) {
                    commentCard.classList.add('has-codes');
                } else {
                    commentCard.classList.remove('has-codes');
                }
            }
        });
}

function deleteCode(codeId, commentId, codesList) {
    fetch(`/delete_code/${codeId}`, {
        method: 'DELETE'
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            loadExistingCodes(commentId, codesList);
        }
    });
}

function exportPostCodes(postId) {
    window.location.href = `/export_codes/${postId}`;
}

function exportAllCodes() {
    window.location.href = '/export_codes';
}
