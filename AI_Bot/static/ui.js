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
    // Messages page: pick up new messages and alerts on its own.
    // Only the two lists are replaced, so the current filter, scroll
    // position and any form the user is filling in stay untouched.
    // -----------------------------------------------------

    var liveSection = document.querySelector("[data-live-url]");
    var lastLiveSnapshot = "";

    function escapeHtml(value) {
        return String(value === null || value === undefined ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function renderLiveMessages(items) {
        var host = document.getElementById("messages-live");

        if (!host) {
            return;
        }

        if (!items.length) {
            host.innerHTML =
                '<div class="empty-state">' +
                    '<span class="empty-icon"><svg class="icon"><use href="#i-messages"/></svg></span>' +
                    '<div><h3>Nothing captured yet</h3>' +
                    '<p>Messages appear here as soon as they arrive.</p></div>' +
                '</div>';
            return;
        }

        host.innerHTML = '<ul class="message-list">' + items.map(function (item) {
            return '<li class="message-row' + (item.is_deleted ? ' deleted' : '') + '">' +
                '<div class="meta">' +
                    '<span class="avatar small">' +
                        escapeHtml(String(item.contact || "?").slice(0, 1).toUpperCase()) +
                    '</span>' +
                    '<strong>' + escapeHtml(item.contact) + '</strong>' +
                    '<span class="muted">' + escapeHtml(item.sent_at) + '</span>' +
                    (item.is_deleted ? '<span class="pill danger">Deleted</span>' : '') +
                '</div>' +
                (item.summary
                    ? '<p class="summary">' + escapeHtml(item.summary) + '</p>'
                    : '') +
                '<p class="raw">' + escapeHtml(item.body) + '</p>' +
            '</li>';
        }).join("") + '</ul>';
    }

    function renderLiveSessions(items) {
        var host = document.getElementById("sessions-live");

        if (!host) {
            return;
        }

        if (!items || !items.length) {
            host.innerHTML =
                '<p class="sessions-empty">No sessions recorded yet. ' +
                'Turn on the eye next to a contact, then wait until ' +
                "they're active on WhatsApp.</p>";
            return;
        }

        host.innerHTML = items.map(function (item) {
            return '<span class="session-chip" title="' +
                    escapeHtml(item.contact) + '">' +
                    '<strong>' + escapeHtml(item.contact) + '</strong>' +
                    '<span>' + escapeHtml(item.start) + ' → ' +
                        escapeHtml(item.end) + ' · ' +
                        escapeHtml(item.minutes) + ' min</span>' +
                '</span>';
        }).join("");
    }

    function renderLiveAlerts(items) {
        var host = document.getElementById("alerts-live");

        if (!host) {
            return;
        }

        if (!items.length) {
            host.innerHTML =
                '<div class="empty-state compact">' +
                    '<span class="empty-icon"><svg class="icon"><use href="#i-bell"/></svg></span>' +
                    '<div><h3>No alerts yet</h3>' +
                    '<p>New messages and deletions will show up here.</p></div>' +
                '</div>';
            return;
        }

        host.innerHTML = '<ul class="alert-list">' + items.map(function (item) {
            var icon = item.kind === "deleted"
                ? "i-trash"
                : (item.kind === "online_session"
                    ? "i-clock"
                    : (item.kind === "summary" ? "i-info" : "i-chat"));
            var tone = item.kind === "deleted"
                ? "danger"
                : ((item.kind === "summary" || item.kind === "online_session")
                    ? "accent"
                    : "success");

            return '<li class="alert-row' + (item.seen ? '' : ' unread') + '">' +
                '<span class="title-icon ' + tone + '">' +
                    '<svg class="icon"><use href="#' + icon + '"/></svg>' +
                '</span>' +
                '<div class="alert-content">' +
                    '<div class="alert-meta">' +
                        '<strong>' + escapeHtml(item.title) + '</strong>' +
                        '<span class="muted">' + escapeHtml(item.time) + '</span>' +
                    '</div>' +
                    '<p class="alert-body">' + escapeHtml(item.body) + '</p>' +
                '</div>' +
                (item.seen
                    ? ''
                    : '<form method="post" action="/alerts/' + encodeURIComponent(item.id) +
                      '/seen"><button type="submit" class="btn ghost small" ' +
                      'title="Mark as seen">Seen</button></form>') +
            '</li>';
        }).join("") + '</ul>';
    }

    function renderLiveActions(unread) {
        var host = document.getElementById("alerts-actions");

        if (!host) {
            return;
        }

        host.innerHTML = unread
            ? '<span class="pill danger">' + escapeHtml(unread) + ' new</span>' +
              '<form method="post" action="/alerts/seen-all">' +
                  '<button type="submit" class="btn ghost small">' +
                      '<svg class="icon"><use href="#i-check"/></svg> Mark all seen' +
                  '</button>' +
              '</form>'
            : '';
    }

    function refreshLive() {
        if (!liveSection) {
            return;
        }

        var url = liveSection.dataset.liveUrl + window.location.search;

        fetch(url, { credentials: "same-origin" })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error("live refresh failed");
                }
                return response.json();
            })
            .then(function (data) {
                var snapshot = JSON.stringify(data);

                if (snapshot === lastLiveSnapshot) {
                    return;
                }

                lastLiveSnapshot = snapshot;
                renderLiveMessages(data.messages || []);
                renderLiveSessions(data.sessions || []);
                renderLiveAlerts(data.alerts || []);
                renderLiveActions(data.unread || 0);
            })
            .catch(function () {
                // Keep whatever is already on screen.
            });
    }

    if (liveSection) {
        refreshLive();
        setInterval(refreshLive, 5000);
    }

    // -----------------------------------------------------
    // Confirm destructive actions
    // -----------------------------------------------------

    document.querySelectorAll("form[data-confirm]").forEach(function (form) {
        form.addEventListener("submit", function (event) {
            if (!window.confirm(form.dataset.confirm)) {
                event.preventDefault();
            }
        });
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
