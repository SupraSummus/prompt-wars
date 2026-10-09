# Vendored front-end libraries

The site serves its third-party CSS and JS itself,
so a library changes only when a commit changes it.
A CDN link that floats on a major version
lets an upstream release restyle every page with no deploy,
and a CDN outage takes the styling down with it.

Each library lives in a directory named after its version,
holding the upstream files byte for byte, its license beside them.
Templates reference the versioned path through `{% static %}`,
so the version a page uses is readable in the template,
and an upgrade is a diff that touches every page using the library.

Sources, as published on npm:

- `pico-2.1.1/`: `@picocss/pico@2.1.1`, `css/pico.min.css`
- `htmx-1.9.12/`: `htmx.org@1.9.12`, `dist/htmx.min.js`
- `chart.js-4.4.4/`: `chart.js@4.4.4`, `dist/chart.umd.js`
  and the source map its last line names,
  which `collectstatic` follows and fails without

## Upgrading

Download the new version into a new directory from the package's npm tarball
(jsDelivr serves the same files at `https://cdn.jsdelivr.net/npm/<package>@<version>/<path>`),
keep the files unmodified,
point the templates at the new path
(`git grep vendor/<name>` finds them),
and delete the old directory in the same commit.
Read the library's changelog before bumping a major version:
Pico restyles plain HTML elements,
so its upgrades show up on pages that never mention it.
