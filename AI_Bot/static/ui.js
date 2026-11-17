/* Shared UI behaviour: theme, navigation, status and small helpers. */

(function () {

    "use strict";

    // -----------------------------------------------------
    // Theme toggle
    // -----------------------------------------------------

    var root = document.documentElement;
    var themeBtn = document.getElementById("theme-btn");

    function applyTheme(theme) {
        root.dataset.theme = theme;

        if (themeBtn) {
            themeBtn.setAttribute(
                "aria-label",
                theme === "dark" ? "Switch to light theme" : "Switch to dark theme"
            );
        }
    }

    applyTheme(root.dataset.theme === "dark" ? "dark" : "light");

    if (themeBtn) {
        themeBtn.addEventListener("click", function () {
            var next = root.dataset.theme === "dark" ? "light" : "dark";
            applyTheme(next);

            try {
                localStorage.setItem("rx-theme", next);
            } catch (error) { /* storage may be unavailable */ }
        });
    }

    // -----------------------------------------------------
    // Mobile sidebar
    // -----------------------------------------------------

    var menuBtn = document.getElementById("menu-btn");
    var sidebar = document.getElementById("sidebar");
    var scrim = document.getElementById("sidebar-scrim");

    function setSidebar(open) {
        if (sidebar) {
            sidebar.classList.toggle("open", open);
        }

        if (scrim) {
            scrim.classList.toggle("open", open);
        }
    }

    if (menuBtn) {
        menuBtn.addEventListener("click", function () {
            setSidebar(!sidebar.classList.contains("open"));
        });
    }

    if (scrim) {
        scrim.addEventListener("click", function () {
            setSidebar(false);
        });
    }

    // -----------------------------------------------------
    // Highlight the current page in the sidebar
    // -----------------------------------------------------

    var path = window.location.pathname;

    document.querySelectorAll(".nav-link[data-nav]").forEach(function (link) {
        var target = link.dataset.nav;
        var isCurrent = target === path || (target === "/qr" && path === "/link");

        if (isCurrent) {
            link.classList.add("active");
        } else {
            link.classList.remove("active");
        }

        if (target === path) {
            link.setAttribute("aria-current", "page");
        }
    });

    document.querySelectorAll(".nav-link").forEach(function (link) {
        link.addEventListener("click", function () {
            if (window.innerWidth <= 860) {
                setSidebar(false);
            }
        });
    });

    // -----------------------------------------------------
    // WhatsApp connection indicator in the sidebar
    // -----------------------------------------------------

    var waDot = document.getElementById("wa-dot");
    var waLabel = document.getElementById("wa-label");

    function setWaState(kind, label) {
        if (!waDot || !waLabel) {
            return;
        }

        waDot.className = "status-dot";

        if (kind) {
            waDot.classList.add(kind);
        }

        waLabel.textContent = label;
    }

    function refreshWaState() {
        if (!waDot) {
            return;
        }

        fetch("/qr/status", { credentials: "same-origin" })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error("status request failed");
                }
                return response.json();
            })
            .then(function (data) {
                if (data.sidecarDown) {
                    setWaState("is-down", "Sidecar is offline");
                } else if (data.connected) {
                    setWaState("is-ok", "WhatsApp linked");
                } else {
                    setWaState(null, "WhatsApp not linked");
                }
            })
            .catch(function () {
                setWaState("is-down", "Sidecar is offline");
            });
    }

    if (waDot) {
        refreshWaState();
        setInterval(refreshWaState, 6000);
    }

    // -----------------------------------------------------
    // Copy the pairing code on click
    // -----------------------------------------------------

    // Delegated, because the QR page can create the code after load.
    document.addEventListener("click", function (event) {

        var codeBox = event.target.closest
            ? event.target.closest("#pairing-code")
            : null;

        if (!codeBox || !navigator.clipboard) {
            return;
        }

        navigator.clipboard.writeText(codeBox.textContent.trim())
            .then(function () {
                var previous = codeBox.title;
                codeBox.title = "Copied!";
                setTimeout(function () {
                    codeBox.title = previous;
                }, 1600);
            })
            .catch(function () { /* clipboard permission denied */ });
    });

    // -----------------------------------------------------
    // Show / hide password on the login page
    // -----------------------------------------------------

    var passwordToggle = document.getElementById("show-password");
    var passwordInput = document.getElementById("password");

    if (passwordToggle && passwordInput) {
        passwordToggle.addEventListener("click", function () {
            var showing = passwordInput.type === "text";
            passwordInput.type = showing ? "password" : "text";
            passwordToggle.textContent = showing ? "Show" : "Hide";
            passwordToggle.setAttribute("aria-label", showing ? "Show password" : "Hide password");
        });
    }

})();
