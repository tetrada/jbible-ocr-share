#!/usr/bin/env bash
set -euo pipefail
BASE=/opt/jbible/importer
URL=https://raw.githubusercontent.com/tetrada/jbible-ocr-share/main
for item in fr88_learning_prompt.py run_fr88_v4_learning.sh fr88_v4_learning_proxy.py fr88_v4_holdout_eval.py test_fr88_learning_prompt.py test_fr88_v4_holdout_eval.py; do
  curl -fsSL --retry 3 "$URL/tools/$item" -o "$BASE/$item"
  echo "Installed $item"
done
curl -fsSL --retry 3 "$URL/training/fr88_ocr_gold.json" -o "$BASE/fr88_ocr_gold.json"
chmod +x "$BASE/run_fr88_v4_learning.sh"
python3 -m py_compile "$BASE/fr88_learning_prompt.py" "$BASE/fr88_v4_holdout_eval.py"
(cd "$BASE" && python3 test_fr88_learning_prompt.py && python3 test_fr88_v4_holdout_eval.py)
"$BASE/run_fr88_v4_learning.sh" --start 31 --end 34 --preflight
echo "Ready: cd $BASE && ./run_fr88_v4_learning.sh --start 31 --end 34"
