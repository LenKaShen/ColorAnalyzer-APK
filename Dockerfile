FROM kivy/buildozer:latest

USER root

# Patch Buildozer 1.5.x to support the new cmdline-tools sdkmanager path.
# The old tools/bin/sdkmanager was removed from modern Android SDK packages.
RUN python3 - <<'EOF'
import re, pathlib
p = pathlib.Path('/home/user/.venv/lib/python3.12/site-packages/buildozer/targets/android.py')
src = p.read_text()
old = """        sdkmanager_path = join(
            self.android_sdk_dir, 'tools', 'bin', sdk_manager_name)
        if not os.path.isfile(sdkmanager_path):
            raise BuildozerException(
                ('sdkmanager path "{}" does not exist, sdkmanager is not'
                 ' installed'.format(sdkmanager_path)))
        return sdkmanager_path"""
new = """        # Try modern cmdline-tools path first, fall back to legacy tools/bin
        candidates = [
            join(self.android_sdk_dir, 'cmdline-tools', 'latest', 'bin', sdk_manager_name),
            join(self.android_sdk_dir, 'tools', 'bin', sdk_manager_name),
        ]
        for sdkmanager_path in candidates:
            if os.path.isfile(sdkmanager_path):
                return sdkmanager_path
        raise BuildozerException(
            'sdkmanager not found in any known location under {}'.format(self.android_sdk_dir))"""
if old in src:
    p.write_text(src.replace(old, new))
    print('Patched sdkmanager path in buildozer android.py')
else:
    print('WARNING: could not find sdkmanager_path block to patch - may already be patched or changed')
EOF

# Use parallel make jobs for all compile steps
ENV MAKEFLAGS="-j8"

WORKDIR /home/user/hostcwd
ENTRYPOINT ["buildozer"]
