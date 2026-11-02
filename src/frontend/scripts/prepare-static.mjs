import { copyFile, mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const source = new URL("../node_modules/bootstrap/", import.meta.url);
const destination = new URL("../static/vendor/bootstrap/", import.meta.url);
const files = [
  ["dist/css/bootstrap.min.css", "bootstrap.min.css"],
  ["dist/css/bootstrap.min.css.map", "bootstrap.min.css.map"],
  ["dist/js/bootstrap.bundle.min.js", "bootstrap.bundle.min.js"],
  ["dist/js/bootstrap.bundle.min.js.map", "bootstrap.bundle.min.js.map"],
  ["LICENSE", "LICENSE"],
];

await mkdir(destination, { recursive: true });
for (const [input, output] of files) {
  await copyFile(new URL(input, source), new URL(output, destination));
}
console.log(`Bootstrap preparado en ${fileURLToPath(destination)}`);
