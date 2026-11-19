// The checkboxes are the actual form fields. The tags are a visual convenience.
document.querySelectorAll('[data-category-picker]').forEach((picker) => {
    const boxes = [...picker.querySelectorAll('input[type="checkbox"]')];
    const summary = picker.querySelector('[data-selected-tags]');
    const bar = picker.querySelector('[data-remove-bar]');
    const placeholder = picker.querySelector('[data-placeholder]').textContent;

    function refresh() {
        const checked = boxes.filter((box) => box.checked);
        summary.textContent = checked.length
            ? `${checked.length} ${checked.length === 1 ? 'category' : 'categories'} selected`
            : placeholder;
        bar.replaceChildren();
        bar.hidden = checked.length === 0;
        checked.forEach((box) => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'remove-category';
            button.textContent = box.dataset.categoryName;
            button.setAttribute('aria-label', `Remove ${box.dataset.categoryName}`);
            const cross = document.createElement('span');
            cross.textContent = '×';
            cross.setAttribute('aria-hidden', 'true');
            button.append(cross);
            button.addEventListener('click', () => {
                box.checked = false;
                refresh();
                picker.querySelector('summary').focus();
            });
            bar.append(button);
        });
    }
    boxes.forEach((box) => box.addEventListener('change', refresh));
    refresh();
});

document.querySelectorAll('form[data-confirm]').forEach((form) => {
    form.addEventListener('submit', (event) => {
        if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
});
