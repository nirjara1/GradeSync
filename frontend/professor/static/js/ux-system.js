(function () {
    'use strict';

    var PATH_KEY = location.pathname + location.search;
    var SCROLL_KEY = 'gs:scroll:' + PATH_KEY;

    function onReady(fn) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', fn);
        } else {
            fn();
        }
    }

    function createToastStack() {
        var stack = document.querySelector('.gs-toast-stack');
        if (stack) return stack;
        stack = document.createElement('div');
        stack.className = 'gs-toast-stack';
        document.body.appendChild(stack);
        return stack;
    }

    function toast(message, opts) {
        opts = opts || {};
        var stack = createToastStack();
        var node = document.createElement('div');
        node.className = 'gs-toast';
        var actions = '';
        if (opts.undoLabel) {
            actions = '<button type="button" class="js-gs-undo">' + opts.undoLabel + '</button>';
        }
        node.innerHTML = '<span>' + message + '</span>' + actions;
        stack.appendChild(node);
        requestAnimationFrame(function () { node.classList.add('show'); });

        var done = false;
        function close() {
            if (done) return;
            done = true;
            node.classList.remove('show');
            setTimeout(function () {
                if (node.parentNode) node.parentNode.removeChild(node);
            }, 180);
        }

        if (opts.onUndo) {
            var undoBtn = node.querySelector('.js-gs-undo');
            if (undoBtn) {
                undoBtn.addEventListener('click', function () {
                    opts.onUndo();
                    close();
                });
            }
        }

        setTimeout(close, opts.duration || 2600);
    }

    function restoreScroll() {
        var raw = sessionStorage.getItem(SCROLL_KEY);
        if (!raw) return;
        sessionStorage.removeItem(SCROLL_KEY);
        var y = parseInt(raw, 10);
        if (!Number.isFinite(y)) return;
        window.scrollTo(0, y);
    }

    function persistScroll() {
        sessionStorage.setItem(SCROLL_KEY, String(window.scrollY || 0));
    }

    function rememberTabs() {
        document.querySelectorAll('[data-persist-tab]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var group = btn.getAttribute('data-tab-group') || 'default';
                var value = btn.getAttribute('data-persist-tab');
                if (!value) return;
                localStorage.setItem('gs:tab:' + PATH_KEY + ':' + group, value);
            });
        });
    }

    function restoreTabs() {
        document.querySelectorAll('[data-persist-tab][data-default-tab]').forEach(function (btn) {
            var group = btn.getAttribute('data-tab-group') || 'default';
            var value = localStorage.getItem('gs:tab:' + PATH_KEY + ':' + group);
            if (!value) return;
            var target = document.querySelector('[data-persist-tab="' + value + '"][data-tab-group="' + group + '"]');
            if (target) target.click();
        });
    }

    function prefetchLink(url) {
        if (!url || !url.startsWith('/') || url.startsWith('//')) return;
        if (document.querySelector('link[rel="prefetch"][href="' + url + '"]')) return;
        var l = document.createElement('link');
        l.rel = 'prefetch';
        l.href = url;
        l.as = 'document';
        document.head.appendChild(l);
    }

    function setupPrefetch() {
        var anchors = document.querySelectorAll('a[href^="/"]');
        anchors.forEach(function (a) {
            a.addEventListener('mouseenter', function () { prefetchLink(a.getAttribute('href')); }, { passive: true });
            a.addEventListener('touchstart', function () { prefetchLink(a.getAttribute('href')); }, { passive: true });
        });
        if ('requestIdleCallback' in window) {
            requestIdleCallback(function () {
                document.querySelectorAll('.sidebar a[href^="/"], .course-card[href^="/"], .course-card-enhanced[href^="/"]').forEach(function (a) {
                    prefetchLink(a.getAttribute('href'));
                });
            }, { timeout: 1200 });
        }
    }

    function setupQuickSearchKey() {
        document.addEventListener('keydown', function (e) {
            if (e.defaultPrevented) return;
            if (e.key !== '/') return;
            var tag = (e.target && e.target.tagName || '').toLowerCase();
            if (tag === 'input' || tag === 'textarea' || e.target.isContentEditable) return;
            var search = document.querySelector('input[type="search"], input[name*="search"], input[id*="search"]');
            if (!search) return;
            e.preventDefault();
            search.focus();
            search.select && search.select();
        });
    }

    function setupDebouncedUrlInputs() {
        var timers = new Map();
        document.querySelectorAll('[data-debounce-url]').forEach(function (input) {
            var delay = Number(input.getAttribute('data-debounce-ms') || 300);
            var param = input.getAttribute('data-param') || input.name || 'q';
            var eventName = (input.tagName || '').toLowerCase() === 'select' ? 'change' : 'input';
            input.addEventListener(eventName, function () {
                if (timers.has(input)) clearTimeout(timers.get(input));
                timers.set(input, setTimeout(function () {
                    var u = new URL(location.href);
                    if (input.value) u.searchParams.set(param, input.value);
                    else u.searchParams.delete(param);
                    history.replaceState({}, '', u.toString());
                    var form = input.form;
                    if (form) form.submit();
                }, delay));
            });
        });
    }

    function setupCommandPalette() {
        var shell = document.createElement('div');
        shell.className = 'gs-cmdk';
        shell.innerHTML = '' +
            '<div class="gs-cmdk-panel" role="dialog" aria-modal="true" aria-label="Command palette">' +
                '<input class="gs-cmdk-input" type="text" placeholder="Type to jump to a page...">' +
                '<div class="gs-cmdk-list"></div>' +
            '</div>';
        document.body.appendChild(shell);
        var input = shell.querySelector('.gs-cmdk-input');
        var list = shell.querySelector('.gs-cmdk-list');
        var items = [];

        document.querySelectorAll('.sidebar a[href]').forEach(function (a) {
            items.push({
                href: a.getAttribute('href'),
                label: a.textContent.trim().replace(/\s+/g, ' ')
            });
        });

        function render(filter) {
            var q = (filter || '').toLowerCase();
            var filtered = items.filter(function (i) { return i.label.toLowerCase().indexOf(q) !== -1; });
            list.innerHTML = filtered.map(function (i) {
                return '<a class="gs-cmdk-item" href="' + i.href + '">' + i.label + '</a>';
            }).join('');
        }

        function open() {
            render('');
            shell.classList.add('open');
            input.value = '';
            setTimeout(function () { input.focus(); }, 0);
        }

        function close() { shell.classList.remove('open'); }

        input.addEventListener('input', function () { render(input.value); });
        shell.addEventListener('click', function (e) { if (e.target === shell) close(); });

        document.addEventListener('keydown', function (e) {
            var isCmdK = (e.key.toLowerCase() === 'k') && (e.metaKey || e.ctrlKey);
            if (isCmdK) {
                e.preventDefault();
                if (shell.classList.contains('open')) close();
                else open();
                return;
            }
            if (e.key === 'Escape' && shell.classList.contains('open')) {
                e.preventDefault();
                close();
            }
        });
    }

    function setupUndoableQuickActions() {
        document.querySelectorAll('form[data-undo-submit]').forEach(function (form) {
            form.addEventListener('submit', function (e) {
                if (form.dataset.undoCommitted === '1') {
                    form.dataset.undoCommitted = '';
                    return;
                }
                e.preventDefault();
                var delay = Number(form.getAttribute('data-undo-delay') || 1400);
                var label = form.getAttribute('data-undo-label') || 'Action queued';
                var timer = setTimeout(function () {
                    form.dataset.undoCommitted = '1';
                    form.submit();
                }, delay);
                toast(label, {
                    undoLabel: 'Undo',
                    duration: delay + 700,
                    onUndo: function () {
                        clearTimeout(timer);
                    }
                });
            });
        });
    }

    function setupSavedTimestamps() {
        document.querySelectorAll('form[data-save-timestamp]').forEach(function (form) {
            var key = form.getAttribute('data-save-key') || ('gs:last-saved:' + location.pathname + ':' + (form.id || form.action || 'form'));
            var targetSel = form.getAttribute('data-save-target');
            var target = targetSel ? document.querySelector(targetSel) : null;
            if (!target) return;

            function fmt(ts) {
                var d = new Date(ts);
                var mins = String(d.getMinutes()).padStart(2, '0');
                var hours = d.getHours() % 12 || 12;
                var ampm = d.getHours() < 12 ? 'AM' : 'PM';
                return 'Saved at ' + hours + ':' + mins + ' ' + ampm;
            }

            var old = localStorage.getItem(key);
            if (old) {
                target.textContent = fmt(Number(old));
                target.classList.add('success');
            }

            form.addEventListener('submit', function () {
                var now = Date.now();
                localStorage.setItem(key, String(now));
                target.textContent = fmt(now);
                target.classList.add('success');
            });
        });
    }

    onReady(function () {
        restoreScroll();
        restoreTabs();
        rememberTabs();
        setupPrefetch();
        setupQuickSearchKey();
        setupDebouncedUrlInputs();
        setupCommandPalette();
        setupUndoableQuickActions();
        setupSavedTimestamps();
        window.addEventListener('beforeunload', persistScroll);

        window.gsUX = {
            toast: toast,
        };
    });
})();
