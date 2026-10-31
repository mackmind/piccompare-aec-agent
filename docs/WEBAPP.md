# The local web page

This page explains the small web page that runs on your own computer. It opens a
report, shows the findings and the evidence cards, and lets you re-check and
export one run - without typing terminal commands. AEC means architecture,
engineering and construction, the industry that designs and builds buildings.

## What it is

The page is a front end for one prepared example pair of floor plans at a time.
From it you can:

- pick a fixture pair and measure it;
- read the report: findings, elements that were not compared, rejected
  candidates, measurements, the report digest and the limitations;
- look at the evidence cards, the small picture crops the report describes;
- re-check the report from its stored fingerprints;
- export the measured overlay and download the files.

It does not measure anything itself. Every step is the same function the command
line and the AI assistant server call (`aec.ops.measure`, `aec.ops.verify`,
`aec.ops.export`), so the terminal, the assistant and the page cannot disagree.
The path is: browser, then `aec.webapp`, then `aec.ops`, then a report file, then
the renderer in `aec.viewer`. Nothing in the page imports the PicCompare engine.

## Start it

```bash
.venv-aec/Scripts/python.exe -m aec serve
```

If the package is installed, `python -m aec serve` is enough. The command binds
the loopback address (it asks for `127.0.0.1`), picks a free port, prints one URL
that carries the session token, and opens your browser at that URL.

| Option | Default | What it does |
|---|---|---|
| `--port` | `0` | the TCP port to use; `0` asks the operating system for a free one |
| `--fixtures` | `fixtures/aec` | the folder searched for fixture pairs; a pair is a subfolder holding `config.json` |
| `--workspace` | `runs/web` | the folder each run is written into; created if it is missing |
| `--no-open` | off | print the URL without opening a browser |

Relative paths are resolved from the directory you run the command in. There is
no option to change the address the server listens on.

Stop it with Ctrl-C, or by closing its input; either way the port is released
and nothing keeps running in the background.

Each measurement is written to its own folder, `<workspace>/<run id>/`, where the
run id is 32 lowercase hexadecimal characters chosen by the server. A run folder
holds `report.json`, a `cards/` folder when evidence cards were requested, and an
`export/` folder once you export. Two runs never share a folder.

## Routes

The page has a small fixed set of addresses. Anything else is refused.

| Method | Path | What it does |
|---|---|---|
| GET | `/` | lists the fixture pairs found under the fixtures folder, with a Measure form for each |
| POST | `/measure` | measures the chosen pair, then redirects to its report page |
| GET | `/run/<id>` | the report: findings, measurements, digest, limitations and evidence cards |
| GET | `/run/<id>/card/<name>` | one evidence card image, served only while its bytes match the hash the report recorded |
| POST | `/run/<id>/verify` | re-checks the report and shows the result, or the reasons it failed |
| POST | `/run/<id>/export` | writes the SVG and DXF overlays into the run's export folder and lists the files |
| GET | `/run/<id>/export/<name>` | one exported file |
| GET | `/tools` | the 12 tools this repository publishes to an AI assistant, with their input schemas; nothing on the page runs a tool |
| GET | `/healthz` | a small JSON answer, `{"ok": true}`, that says the server is up |

Every refusal is a JSON answer with the HTTP status that describes it, such as
`403` for a missing token or `404` for a name the report does not record.

## Security model

Stated plainly, this is what the page does and does not protect.

- **Loopback only.** The server checks the address against a short allowlist -
  `127.0.0.1`, `::1` and `localhost` - before it opens a socket, and refuses to
  start for anything else. The command has no switch that widens this.
- **One name per server.** A request must address the server as `127.0.0.1`,
  `localhost` or `[::1]` on the port the server is bound to. A page on another
  host name that resolves to this address - a DNS-rebinding page - sends that
  other name and is refused with `403` before anything is served, so it cannot
  read the token from the start page or drive an action with it.
- **One session token per server process.** It is created at random when the
  server starts and printed inside the URL. Every action that measures, verifies
  or exports must present it; a request without it, or with another run's token,
  is refused. Reading a page does not need the token.
- **No authentication.** There are no accounts, no passwords and no user roles.
  Anyone who can reach the port can read the pages the server is running for. The
  token is printed in your terminal, so treat that line as private while the
  server runs.
- **No remote access.** The page listens on this machine only, and there is no
  supported way to reach it from another machine.
- **No file upload.** The only thing a request may send is a small form: a pair
  name and a token. A body above 64 KiB is refused, and a body that is not a
  URL-encoded form is treated as empty, which means no token and a refusal.
- **Names are checked, not trusted.** A run id must be 32 lowercase hexadecimal
  characters, a file name is restricted to letters, digits, dot, dash and
  underscore, and every requested file, the folder holding it and the run's
  `report.json` must resolve directly inside the run folder. A `cards/` or
  `export/` folder, or a report file, that is a link to somewhere else is refused
  rather than followed. A card is served only while its bytes hash to the digest
  the report recorded, so a picture edited after the run is refused rather than
  shown.
- **Every answer carries the same headers**, including a content security policy
  that allows no script and no remote asset, `nosniff`, `no-referrer`,
  `no-store` and `DENY` framing. The pages load no JavaScript and no file from
  the network.
- **Errors are short.** A failure leaves as one JSON answer with absolute paths
  and the session token removed. The full detail, including a traceback when
  something unexpected breaks, is written to your terminal for the operator to
  read.

The page is **not a hosted service**. It is one process on one machine for the
length of a review. Do not expose it through a proxy, a tunnel or a public
address; it has no defence for that situation, by design.

## What it is not

- **Not a second measurement engine.** It calls the same measurement function as
  everything else; it contains no comparison logic of its own.
- **Not a report editor.** You cannot change a finding, a measurement or a
  limitation, and you cannot re-run a saved report with different settings. A new
  measurement is a new run with a new folder.
- **Not a viewer for the separate PicCompare desktop application.** The page
  shows AEC reports only. The desktop user interface shown in the demo video
  belongs to that separate application and is not part of this repository.

## After the event

The renderer is deliberately plain: one HTML document, inline style, no
JavaScript and no remote asset. That means the same page can later be written as
a static report viewer - a file you open from a folder, a chat attachment or a CI
artifact - with no server behind it. The command line already does this with
`aec view`, which writes the same document to a single file.

Turning this page into a shared service would be a different piece of work. It
would need authentication, encrypted transport (TLS), storage that keeps one
tenant's runs apart from another's, and rate limiting. None of that is here, and
none of it is claimed.
