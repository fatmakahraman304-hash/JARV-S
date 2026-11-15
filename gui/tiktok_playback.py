"""Start the visible TikTok video in the existing embedded page."""

PLAY_VISIBLE_VIDEO = r"""(() => {
    if (location.protocol !== 'https:' ||
        !['tiktok.com', 'www.tiktok.com'].includes(location.hostname) ||
        (location.port && location.port !== '443')) return 'no-video';

    let selected = null;
    let largest = 0;
    for (const video of document.querySelectorAll('video')) {
        const rect = video.getBoundingClientRect();
        const style = getComputedStyle(video);
        if (style.visibility !== 'visible' || style.display === 'none' ||
            video.closest('[hidden], [inert], [aria-hidden="true"]')) continue;
        const width = Math.max(0, Math.min(innerWidth, rect.right) - Math.max(0, rect.left));
        const height = Math.max(0, Math.min(innerHeight, rect.bottom) - Math.max(0, rect.top));
        const area = width * height;
        if (area > largest) {
            selected = video;
            largest = area;
        }
    }
    if (!selected || largest < 1000) return 'no-video';
    const state = {element: selected, result: 'pending'};
    globalThis.jarvisTikTokPlayback = state;
    if (!selected.paused && !selected.ended && selected.readyState >= 3) {
        return state.result = 'playing';
    }
    selected.play().then(() => {
        state.result = 'playing';
    }).catch(error => {
        state.result = error.name === 'NotAllowedError' ? 'needs-click' : 'failed';
    });
    return state.result;
})()"""

PLAYBACK_RESULT = """(() => {
    const state = globalThis.jarvisTikTokPlayback;
    return state?.element.isConnected ? state.result : 'no-video';
})()"""
