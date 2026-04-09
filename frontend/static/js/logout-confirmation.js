document.addEventListener("DOMContentLoaded", () => {
    const modal = document.getElementById("logoutConfirmModal");
    const confirmButton = document.getElementById("logoutConfirmSubmit");

    if (!modal || !confirmButton) {
        return;
    }

    const closeButtons = modal.querySelectorAll("[data-logout-close]");
    let pendingForm = null;

    const openModal = (form) => {
        pendingForm = form;
        modal.classList.add("is-open");
        modal.setAttribute("aria-hidden", "false");
    };

    const closeModal = () => {
        modal.classList.remove("is-open");
        modal.setAttribute("aria-hidden", "true");
        pendingForm = null;
    };

    document.querySelectorAll(".js-logout-trigger").forEach((trigger) => {
        trigger.addEventListener("click", (event) => {
            event.preventDefault();
            const form = trigger.closest("form.js-logout-form");
            if (!form) {
                return;
            }
            openModal(form);
        });
    });

    closeButtons.forEach((button) => {
        button.addEventListener("click", closeModal);
    });

    confirmButton.addEventListener("click", () => {
        if (pendingForm) {
            pendingForm.submit();
        }
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && modal.classList.contains("is-open")) {
            closeModal();
        }
    });
});
