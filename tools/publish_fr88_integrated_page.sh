#!/usr/bin/env bash
# Publish only concise, text-only marker coordinates + individual link proposals.
# No copyrighted scan JPEGs, raw DeepSeek provider payloads or original page text.
set -euo pipefail
[[ "$(id -u)" -eq 0 ]] || { echo "Run as root" >&2; exit 2; }
ROOT=/opt/jbible/ocr-share-git
SRC=/opt/jbible/data/raw/jbible_fr88_integrated_v1
DEST=fr88_integrated_v1
[[ -d "$ROOT/.git" && -s /root/.ssh/jbible_ocr_share ]] || {
  echo "Missing existing JBible Git checkout/SSH deploy key" >&2; exit 2;
}
[[ -s "$SRC/progress.json" ]] || { echo "Run integrated page scanner first" >&2; exit 2; }
export GIT_SSH_COMMAND='ssh -i /root/.ssh/jbible_ocr_share -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new'
(
  flock -x 9
  [[ "$(git -C "$ROOT" rev-parse --abbrev-ref HEAD)" == "main" ]] || exit 3
  if [[ -n "$(git -C "$ROOT" status --porcelain --untracked-files=normal)" ]]; then
    echo "Existing JBible Git checkout has unsynced changes; retry after normal sync" >&2
    exit 3
  fi
  git -C "$ROOT" fetch --quiet origin main
  git -C "$ROOT" merge --ff-only origin/main
  mkdir -p "$ROOT/$DEST"
  python3 - "$SRC" "$ROOT/$DEST" <<'PY'
import json,sys
from pathlib import Path
src,dest=Path(sys.argv[1]),Path(sys.argv[2])
summary=json.loads((src/"progress.json").read_text(encoding="utf-8"))
pages=[]
for fn in sorted(src.glob("image_????.bundle.json")):
    j=json.loads(fn.read_text(encoding="utf-8"))
    edges=[]
    for e in j.get("atomic_source_to_destination_links",[]):
        d=e.get("destination") or {}
        s=e.get("source") or {}
        edges.append({
            "edge_id":e["edge_id"],"margin_row_id":e["row_id"],
            "column":e["column"],"margin_y_fraction":e["margin_y_fraction"],
            "printed_margin_line":e["printed_margin_line"],
            "source_book_code":s.get("book_code"),
            "source_chapter":s.get("chapter"),"source_verse":s.get("verse"),
            "source_y_interval":s.get("source_verse_interval"),
            "target_segment_index":e["target_segment_index"],
            "target_book_code":d.get("book_code"),
            "target_chapter":d.get("chapter"),
            "target_verse":d.get("verse"),
            "target_end_chapter":d.get("end_chapter"),
            "target_end_verse":d.get("end_verse"),
            "target_type":d.get("type"),"target_suffix":d.get("suffix"),
            "target_literal":d.get("literal"),
            "parse_status":d.get("status"),
            "status":e["status"],"qa_reasons":e.get("qa_reasons",[]),
            "accepted_automatically":e.get("accepted_automatically",False),
            "human_review_required":e.get("human_review_required",True),
            "hard_exceptions":e.get("hard_exceptions",[]),
            "source_alignment_estimate_flags":e.get("source_alignment_estimate_flags",[]),
            "possible_adjacent_source_verses":e.get("possible_adjacent_source_verses",[]),
            "editorial_relation_marker":e.get("editorial_relation_marker"),
            "destination_interpretation_flags":e.get("destination_interpretation_flags",[]),
            "human_verified":e.get("scan_human_verified",False),
            "human_review":e.get("user_review"),
            "original_automated_link":e.get("original_automated_link"),
            "sql_ready":False
        })
    markers={side:[{
        "chapter":v.get("chapter"),"verse":v.get("verse"),
        "y_fraction":v.get("y_fraction"),"confidence":v.get("confidence"),
        "ocr_original_chapter":v.get("ocr_original_chapter"),
        "chapter_ocr_repair_evidence":v.get("chapter_ocr_repair_evidence")
    } for v in j.get("verse_markers_by_column",{}).get(side,[])]
      for side in ("L","R")}
    head=j.get("printed_running_head",{})
    pages.append({
        "image_page":j["image_page"],"page_book":j.get("page_book"),
        "running_head":{k:head.get(k) for k in (
            "header_position","boundary_role","chapter","verse","book_code",
            "confidence","scan_confidence","visible","raw")},
        "main_text_verse_markers":markers,
        "source_to_destination_edges":edges,
        "summary":j.get("summary"),"page_flags":j.get("quality_flags"),
        "legacy_margin_comparison":j.get("legacy_margin_comparison")
    })
output={
 "schema":"jbible.fr88.integrated-page-git-report.v1",
 "progress":summary,
 "pages":pages,
 "notice":"Text-only automatically accepted source-to-target links and rare hard exceptions. Acceptance is operational, not an independently measured correctness claim; no SQL writes. Images and provider responses remain on private VPS.",
 "canonical_links_verified":0,"sql_writes":False
}
target=dest/"pilot_report.json"
tmp=dest/"pilot_report.json.tmp"
tmp.write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
tmp.replace(target)
print("PREPARED:",len(pages),"page bundles,",
      sum(len(x["source_to_destination_edges"]) for x in pages),"atomic links")
PY
  git -C "$ROOT" add -- "$DEST/pilot_report.json"
  if git -C "$ROOT" diff --cached --quiet; then
    if [[ "$(git -C "$ROOT" rev-list --count origin/main..HEAD)" -gt 0 ]]; then
      git -C "$ROOT" push origin HEAD:main
    else
      echo "Latest integrated report already published"
    fi
    exit 0
  fi
  git -C "$ROOT" commit -m "Publish text-only full-page verse geometry and atomic Bible link proposals"
  git -C "$ROOT" push origin HEAD:main
  echo "PUBLISHED https://github.com/tetrada/jbible-ocr-share/blob/main/$DEST/pilot_report.json"
) 9>/run/jbible-github-sync.lock
