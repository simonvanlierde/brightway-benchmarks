<script lang="ts">
let { size = 24 }: { size?: number } = $props();
</script>

<svg class="brand-mark" width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
  <rect width="32" height="32" fill="var(--page)" />
  <rect x="0.5" y="0.5" width="31" height="31" fill="none" stroke="var(--grid)" stroke-width="1" />
  <!-- Benchmark baseline -->
  <line x1="4" y1="26" x2="28" y2="26" stroke="var(--line)" stroke-width="1.2" />
  <!-- Benchmark Bar 1: SuperLU baseline (grey-blue) -->
  <rect x="5.5" y="18" width="4.5" height="8" fill="var(--axis)" />
  <!-- Benchmark Bar 2: PyPardiso (series blue) -->
  <rect x="12" y="12" width="4.5" height="14" fill="var(--s1)" />
  <!-- Position 3: Brightway Triangulated Leaf (optimal) -->
  <g fill="var(--better)">
    <polygon points="18.5,25.5 15.5,18 20,18" fill-opacity="0.35" />
    <polygon points="18.5,25.5 20,18 25,22" fill-opacity="0.25" />
    <polygon points="20,18 25,22 27.5,16" fill-opacity="0.45" />
    <polygon points="15.5,18 17.5,11 22,12" fill-opacity="0.5" />
    <polygon points="15.5,18 20,18 22,12" fill-opacity="0.3" />
    <polygon points="20,18 22,12 27.5,16" fill-opacity="0.4" />
    <polygon points="22,12 27.5,16 27,10" fill-opacity="0.6" />
    <polygon points="17.5,11 25.5,5 22,12" fill-opacity="0.75" />
    <polygon points="22,12 25.5,5 27,10" fill-opacity="0.85" />
  </g>
  <!-- Leaf contour and triangulation wireframe (Brightway signature) -->
  <path
    d="M18.5 25.5C14.5 18 17 9 25.5 5C29 11 29 21 18.5 25.5ZM18.5 25.5L25.5 5M15.5 18H20L27.5 16M17.5 11L22 12L27 10M18.5 25.5L25 22L27.5 16"
    stroke="currentColor"
    stroke-width="0.75"
    stroke-linecap="round"
    stroke-linejoin="round"
    fill="none"
  />
  <!-- Apex measurement target node -->
  <rect x="24.5" y="4" width="2" height="2" fill="currentColor" />
</svg>
