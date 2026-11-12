#!/bin/sh
# ExecStartPost of the Ollama service: Ollama must have found the discrete GPU.
#
# Without it, Ollama would load Qwen3-30B-A3B on CPU only (mmap off, ~18 GiB), which does not
# fit this machine. Failing here makes systemd stop Ollama before any model is loaded and start
# it again (Restart=on-failure), with the GPU woken by banana-ollama-gpu-wake.sh.
i=0
line=""
while [ -z "$line" ] && [ $i -lt 40 ]; do
  line=$(journalctl --user -u ollama "_PID=$MAINPID" --no-pager -o cat 2>/dev/null \
    | grep '"inference compute"')
  [ -z "$line" ] && sleep 0.5
  i=$((i + 1))
done
if echo "$line" | grep -q 'type=discrete'; then
  echo "banana-gpu-check: Ollama found the discrete GPU"
  exit 0
fi
echo "banana-gpu-check: Ollama started without the discrete GPU (${line:-no inference compute line}); restarting it" >&2
exit 1
