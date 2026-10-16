import { defineConfig } from "zfb/config";
import { zudoDoc } from "@takazudo/zudo-doc/config";

export default defineConfig(
  zudoDoc({
    siteName: "zudo-stl-fix",
    siteDescription:
      "Local, conservative STL check and repair for macOS: drop files, review the report, save verified copies.",
    locales: {
      ja: {
        label: "JA",
        dir: "src/content/docs-ja",
      },
    },
    githubUrl: "https://github.com/Takazudo/zudo-stl-fix",
    llmsTxt: true,
    sidebarResizer: true,
    sidebarToggle: true,
    tocToggle: true,
    imageEnlarge: true,
    dynamicPageTransition: true,
    docHistory: true,
    bodyFootUtilArea: { docHistory: true, viewSourceLink: true },
    assetViewer: true,
    footer: {
      links: [],
      copyright: "Built with zudo-doc.",
    },
    headerNav: [
      {
        label: "Getting Started",
        labelKey: "nav.getting-started",
        path: "/docs/getting-started",
        categoryMatch: "getting-started",
      },
      {
        label: "App Guide",
        labelKey: "nav.app-guide",
        path: "/docs/app-guide",
        categoryMatch: "app-guide",
      },
      {
        label: "Concepts",
        labelKey: "nav.concepts",
        path: "/docs/concepts",
        categoryMatch: "concepts",
      },
      {
        label: "CLI",
        labelKey: "nav.cli",
        path: "/docs/cli",
        categoryMatch: "cli",
      },
      {
        label: "Reference",
        labelKey: "nav.reference",
        path: "/docs/reference",
        categoryMatch: "reference",
      },
      {
        label: "Develop",
        labelKey: "nav.develop",
        path: "/docs/develop",
        categoryMatch: "develop",
      },
    ],
    translations: {
      en: {
        "nav.getting-started": "Getting Started",
        "nav.app-guide": "App Guide",
        "nav.concepts": "Concepts",
        "nav.cli": "CLI",
        "nav.reference": "Reference",
        "nav.develop": "Develop",
      },
      ja: {
        "nav.getting-started": "はじめに",
        "nav.app-guide": "アプリの使い方",
        "nav.concepts": "基本概念",
        "nav.cli": "CLI",
        "nav.reference": "リファレンス",
        "nav.develop": "開発",
      },
    },
    headerRightItems: [
      {
        type: "component",
        component: "github-link",
      },
      {
        type: "component",
        component: "theme-toggle",
      },
      {
        type: "component",
        component: "search",
      },
      {
        type: "component",
        component: "language-switcher",
      },
    ],
  }),
);
