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
        path: "/docs/getting-started",
        categoryMatch: "getting-started",
      },
      {
        label: "App Guide",
        path: "/docs/app-guide",
        categoryMatch: "app-guide",
      },
      {
        label: "Concepts",
        path: "/docs/concepts",
        categoryMatch: "concepts",
      },
      {
        label: "CLI",
        path: "/docs/cli",
        categoryMatch: "cli",
      },
      {
        label: "Reference",
        path: "/docs/reference",
        categoryMatch: "reference",
      },
      {
        label: "Develop",
        path: "/docs/develop",
        categoryMatch: "develop",
      },
    ],
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
