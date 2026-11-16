// Render the example attempts as notebook pages, for scripts/eval_transcription.py.
// The maths is typeset by KaTeX and the words are in a handwriting font, so these are easier to read than real
// handwriting: they test whether transcription keeps errors, not how well it reads a student's hand.
// Usage: node scripts/render_photos.js   (needs Playwright)
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const exercises = JSON.parse(fs.readFileSync(path.join(root, "data/demo/exercises.json"), "utf8")).exercises;
const out = path.join(root, "data/demo/photos");

const escape = (text) => text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const page = (statement, lines, tilt) => `<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Caveat:wght@500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css">
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js"></script>
<style>body{margin:0;background:#f6f5ef;font:32px/1.7 'Caveat',cursive;color:#1d2f7a;padding:36px 56px;width:960px;
background-image:linear-gradient(#c7d1ea 1px,transparent 1px);background-size:100% 54px;transform:rotate(${tilt}deg)}
.katex{font-size:.82em;color:#1d2f7a} p{margin:0 0 6px} .st{font-weight:500;text-decoration:underline}</style></head>
<body><p class="st">${escape(statement)}</p>${lines.map((l) => `<p>${escape(l)}</p>`).join("")}
<script>renderMathInElement(document.body,{delimiters:[{left:"$",right:"$",display:false}]})</script></body></html>`;

(async () => {
  const browser = await chromium.launch();
  const tab = await browser.newPage({ viewport: { width: 1072, height: 600 } });
  let n = 0;
  for (const exercise of exercises) {
    for (const attempt of exercise.attempts) {
      const tilt = ((n++ % 5) - 2) * 0.6;
      await tab.setContent(page(exercise.statement, attempt.text.split("\n"), tilt), { waitUntil: "networkidle" });
      const height = await tab.evaluate(() => document.body.scrollHeight + 40);
      await tab.setViewportSize({ width: 1072, height });
      const file = path.join(out, `${exercise.id.replace(":", "-")}-${attempt.kind}.jpg`);
      await tab.screenshot({ path: file, type: "jpeg", quality: 82 });
      console.log(file);
    }
  }
  await browser.close();
})();
