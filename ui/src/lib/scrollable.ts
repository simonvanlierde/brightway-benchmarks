/**
 * A Svelte action for a scroll region: it takes keyboard focus, and the `overflowing` class that
 * shades its edge, only while its content is wider than it. ONCHANGE hears each change.
 */
export function scrollable(element: HTMLElement, onchange?: (overflowing: boolean) => void) {
  let tell = onchange;
  const update = () => {
    const over = element.scrollWidth > element.clientWidth;
    if (over) element.tabIndex = 0;
    else element.removeAttribute("tabindex");
    element.classList.toggle("overflowing", over);
    tell?.(over);
  };
  const observer = new ResizeObserver(update);
  observer.observe(element);
  if (element.firstElementChild) observer.observe(element.firstElementChild);
  update();
  return {
    update(next?: (overflowing: boolean) => void) {
      tell = next;
    },
    destroy: () => observer.disconnect(),
  };
}
