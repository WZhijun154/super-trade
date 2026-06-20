// @ts-check

/** @type {import('@docusaurus/plugin-content-docs').SidebarsConfig} */
const sidebars = {
  docsSidebar: [
    'intro',
    'getting-started',
    'architecture',
    {
      type: 'category',
      label: 'Layers',
      items: [
        'layers/data',
        'layers/sources',
        'layers/ingest',
        'layers/metrics',
        'layers/backtest',
        'layers/viz',
      ],
    },
  ],
};

export default sidebars;
