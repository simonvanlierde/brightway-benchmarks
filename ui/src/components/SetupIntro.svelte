<script lang="ts">
// Setup's heading and intro. The page draws them before its script runs (index.astro), and the viewer
// again while the data loads and once it has, so they stay in place throughout.
let { title, intro }: { title: string; intro: string } = $props();
</script>

<header class="home-intro">
  <h1>{title}</h1>
  <p>Which Brightway packages work together, and which combination runs your LCA fastest? Every night we check that the latest <a href="https://docs.brightway.dev/en/latest/">Brightway</a> releases install and work together on Linux, macOS and Windows. {intro}</p>
</header>
