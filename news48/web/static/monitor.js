(function () {
    const root = document.querySelector('[data-monitor-root]');
    if (!root) return;

    const refreshButton = root.querySelector('[data-monitor-refresh]');
    const refreshLabel = root.querySelector('[data-monitor-last-refresh-label]');

    function clampPercentage(value) {
        return Math.max(0, Math.min(100, Number(value) || 0));
    }

    function getNow() {
        return new Date();
    }

    function parseDate(value) {
        if (!value || value === '—') return null;
        const date = new Date(value);
        return Number.isNaN(date.getTime()) ? null : date;
    }

    function formatAbsoluteDate(value) {
        const date = parseDate(value);
        if (!date) return value ?? '—';

        return new Intl.DateTimeFormat('en-GB', {
            day: '2-digit',
            month: 'short',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            hour12: false
        }).format(date).replace(',', ',');
    }

    function formatRelativeDate(value) {
        const date = parseDate(value);
        if (!date) return value ?? '—';

        const diffMs = getNow().getTime() - date.getTime();
        const diffMinutes = Math.max(0, Math.round(diffMs / 60000));

        if (diffMinutes < 1) return 'just now';
        if (diffMinutes < 60) return `${diffMinutes}m ago`;

        const diffHours = Math.round(diffMinutes / 60);
        if (diffHours < 24) return `${diffHours}h ago`;

        const diffDays = Math.round(diffHours / 24);
        if (diffDays < 7) return `${diffDays}d ago`;

        return formatAbsoluteDate(value);
    }

    function formatRelativeDateWithTime(value) {
        const date = parseDate(value);
        if (!date) return value ?? '—';

        const time = new Intl.DateTimeFormat('en-GB', {
            hour: '2-digit',
            minute: '2-digit',
            hour12: false
        }).format(date);

        const relative = formatRelativeDate(value);
        return relative === formatAbsoluteDate(value) ? relative : `${time} (${relative})`;
    }

    function applyDateFormatting(scope = root) {
        scope.querySelectorAll('[data-format="datetime"]').forEach((node) => {
            const raw = node.dataset.rawValue ?? node.textContent?.trim() ?? '—';
            node.dataset.rawValue = raw;
            node.textContent = formatAbsoluteDate(raw);
        });

        scope.querySelectorAll('[data-format="relative-datetime"]').forEach((node) => {
            const raw = node.dataset.rawValue ?? node.textContent?.trim() ?? '—';
            node.dataset.rawValue = raw;
            node.textContent = formatRelativeDateWithTime(raw);
        });
    }

    function setValue(path, value) {
        root.querySelectorAll(`[data-field="${path}"]`).forEach((node) => {
            const nextValue = value ?? '—';
            node.dataset.rawValue = String(nextValue);
            node.textContent = nextValue;
        });
    }

    function setBar(path, percent) {
        root.querySelectorAll(`[data-bar="${path}"]`).forEach((node) => {
            node.style.width = `${clampPercentage(percent)}%`;
        });
    }

    function setNote(path, text) {
        root.querySelectorAll(`[data-note="${path}"]`).forEach((node) => {
            node.textContent = text;
        });
    }

    function updateDerived(data) {
        const articles = data.articles || {};
        const total = Number(articles.total || 0);
        const parsed = Number(articles.parsed || 0);
        const unparsed = Number(articles.unparsed || 0);
        const noContent = Number(articles.no_content || 0);
        const failures = Number(articles.download_failures || 0) + Number(articles.parse_failures || 0);

        const parsedRate = total ? ((parsed / total) * 100).toFixed(1) : '0.0';
        const unparsedRate = total ? ((unparsed / total) * 100).toFixed(1) : '0.0';
        const noContentRate = total ? ((noContent / total) * 100).toFixed(1) : '0.0';

        root.querySelectorAll('[data-field-derived="parse_coverage"]').forEach((node) => {
            node.textContent = `${parsedRate}%`;
        });
        root.querySelectorAll('[data-field-derived="failures_total"]').forEach((node) => {
            node.textContent = failures;
        });

        setNote('articles.parsed', `${parsedRate}% of tracked articles`);
        setNote('articles.unparsed', `${unparsedRate}% still in queue`);
        setNote('articles.no_content', `${noContentRate}% source friction`);
    }

    function updateStats(data) {
        setValue('db_size_mb', data.db_size_mb);
        [
            'articles.total', 'articles.parsed', 'articles.unparsed', 'articles.no_content', 'articles.download_backlog', 'articles.parse_backlog', 'articles.malformed', 'articles.articles_today', 'articles.articles_this_week', 'articles.oldest_unparsed_at',
            'sentiment.positive', 'sentiment.neutral', 'sentiment.negative',
            'feeds.total', 'feeds.never_fetched', 'feeds.stale',
            'fetches.total', 'fetches.avg_articles_per_fetch', 'fetches.last_fetch_at',
            'retention.articles_within_48h', 'retention.articles_expired', 'retention.retention_rate', 'retention.oldest_article', 'retention.newest_article',
            'plans.pending', 'plans.executing', 'plans.completed', 'plans.failed',
            'health.table_counts.articles', 'health.table_counts.feeds', 'health.table_counts.fetches', 'health.table_counts.claims'
        ].forEach((path) => {
            const value = path.split('.').reduce((acc, key) => (acc ? acc[key] : undefined), data);
            setValue(path, value);
        });

        const total = Number(data.articles?.total || 0);
        setBar('articles.parsed', total ? (Number(data.articles?.parsed || 0) / total) * 100 : 0);
        setBar('articles.unparsed', total ? (Number(data.articles?.unparsed || 0) / total) * 100 : 0);
        setBar('articles.no_content', total ? (Number(data.articles?.no_content || 0) / total) * 100 : 0);
        setBar('retention.retention_rate', Number(data.retention?.retention_rate || 0));
        updateDerived(data);
        applyDateFormatting();
    }

    function refresh() {
        applyDateFormatting();
        if (refreshLabel) {
            refreshLabel.textContent = formatRelativeDateWithTime(getNow().toISOString());
        }
    }

    root.querySelectorAll('[data-width]').forEach((node) => {
        node.style.width = `${clampPercentage(node.getAttribute('data-width'))}%`;
    });

    applyDateFormatting();

    if (refreshButton) refreshButton.addEventListener('click', refresh);
})();
