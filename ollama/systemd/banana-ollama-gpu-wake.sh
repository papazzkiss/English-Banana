#!/bin/sh
# ExecStartPre of the Ollama service: wake the discrete GPU and wait until it is active.
#
# The laptop powers the RX 6500M off when idle (runtime PM, BOCO). If Ollama probes the GPUs
# while the card is still resuming, it does not see it and runs on CPU only, and a CPU-only load
# of Qwen3-30B-A3B needs ~18 GiB of RAM: the kernel OOM-killed it on 2026-09-30 (OOM_AUDIT.md).
# Opening the card's render node resumes it synchronously.
DEV="${BANANA_GPU_PCI:-0000:03:00.0}"
NODE="/dev/dri/by-path/pci-$DEV-render"
STATUS="/sys/bus/pci/devices/$DEV/power/runtime_status"

if [ ! -e "$NODE" ]; then
  echo "banana-gpu-wake: no render node for $DEV; nothing to wake"
  exit 0
fi
exec 3<>"$NODE" || { echo "banana-gpu-wake: cannot open $NODE"; exit 0; }
i=0
while [ "$(cat "$STATUS" 2>/dev/null)" != "active" ] && [ $i -lt 60 ]; do
  sleep 0.5
  i=$((i + 1))
done
echo "banana-gpu-wake: $DEV is $(cat "$STATUS" 2>/dev/null)"
sleep 1  # let the driver finish resuming before Ollama enumerates the devices
exec 3>&-
exit 0
