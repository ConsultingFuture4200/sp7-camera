#!/bin/bash
# Make linux-ipu4p the default Limine boot entry. RUN AS ROOT.
# Edits only the `default_entry:` header line of /boot/limine.conf, which
# limine-entry-tool writes at initial generation and does not touch afterwards
# (CHANGELOG: "Set default_entry: 2 ... during initial limine.conf generation").
set -e
CONF=/boot/limine.conf
TARGET=${1:-linux-ipu4p}
[ -f "$CONF" ] || { echo "ABORT: $CONF not found"; exit 1; }

# entry names as Limine sees them: the OS submenu and the kernel sub-entry
OS=$(grep -m1 -oE '^/\+?[A-Za-z].*' "$CONF" | sed -E 's#^/\+?##; s/[[:space:]]+$//')
[ -n "$OS" ] || { echo "ABORT: no top-level OS entry found in $CONF"; exit 1; }
grep -qE "^[[:space:]]*//\+?${TARGET}[[:space:]]*$" "$CONF" || {
  echo "ABORT: no kernel entry named '$TARGET' under '$OS'. Entries present:"; grep -E '^[[:space:]]*//' "$CONF" | sed 's/^/    /'; exit 1; }
cat /etc/limine-entry-tool.conf /etc/limine-entry-tool.d/*.conf 2>/dev/null | grep -qE '^ENABLE_ENROLL_LIMINE_CONFIG=yes' && {
  echo "ABORT: config enrolment is ON; editing limine.conf without re-enrolling would break boot"; exit 1; }

BAK="$CONF.before-default-$(date +%Y%m%d-%H%M%S)"
cp -a "$CONF" "$BAK"
echo "backup: $BAK"
echo "before: $(grep -E '^default_entry:' "$CONF" || echo '(no default_entry line)')"

if grep -qE '^default_entry:' "$CONF"; then
  sed -i "s|^default_entry:.*|default_entry: ${OS}/${TARGET}|" "$CONF"
else
  sed -i "0,/^timeout:/s||&\ndefault_entry: ${OS}/${TARGET}|" "$CONF"
fi
echo "after:  $(grep -E '^default_entry:' "$CONF")"
echo
echo "boot menu now:"; limine-entry-tool --tree 2>/dev/null | sed 's/^/  /'
echo
echo "Default is '${OS}/${TARGET}'. Rollback:  sudo cp '$BAK' $CONF"
