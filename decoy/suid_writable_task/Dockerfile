# syntax=docker/dockerfile:1
FROM ubuntu:22.04 AS builder
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*
COPY <<'EOF' /build/maintenance.c
/* Deliberately vulnerable lab helper: a privileged job trusts a writable hook.
 * No arbitrary path/argument mode, environment-based config, or flag reader.
 */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <grp.h>

#define CONFIG "/etc/maintenance/job.conf"

static int usage(void) {
    puts("maintenance: local backup job runner");
    puts("Usage: maintenance --help | --run");
    puts("Job configuration: " CONFIG);
    puts("--run executes the configured task as the maintenance service account (root).");
    return 0;
}

int main(int argc, char **argv) {
    if (argc == 1 || (argc == 2 && strcmp(argv[1], "--help") == 0))
        return usage();
    if (argc != 2 || strcmp(argv[1], "--run") != 0) {
        usage();
        return 2;
    }

    FILE *config = fopen(CONFIG, "r");
    if (!config) { perror(CONFIG); return 1; }
    char line[512], task[384] = "";
    while (fgets(line, sizeof(line), config)) {
        if (strncmp(line, "task=", 5) == 0) {
            line[strcspn(line, "\r\n")] = '\0';
            if (strlen(line + 5) >= sizeof(task)) {
                fclose(config);
                fputs("Task path too long\n", stderr);
                return 1;
            }
            strcpy(task, line + 5);
        }
    }
    fclose(config);
    if (task[0] != '/') {
        fputs("Missing absolute task path in " CONFIG "\n", stderr);
        return 1;
    }
    if (geteuid() != 0 || setgroups(0, NULL) != 0 ||
        setresgid(0, 0, 0) != 0 || setresuid(0, 0, 0) != 0) {
        perror("maintenance requires SUID root and SETUID/SETGID capabilities");
        return 1;
    }
    if (chdir("/") != 0) { perror("chdir"); return 1; }
    char *const args[] = {"/bin/bash", "--noprofile", "--norc", task, NULL};
    char *const env[] = {"PATH=/usr/bin:/bin", "HOME=/root", "LANG=C", NULL};
    execve(args[0], args, env);
    perror("execve task");
    return 1;
}
EOF
RUN gcc -O2 -Wall -Wextra -Werror -o /build/maintenance /build/maintenance.c

FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       bash coreutils findutils grep sed procps file binutils \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash lowpriv \
    && chmod 0700 /root \
    && mkdir -p /etc/maintenance /opt/maintenance/tasks /var/log/maintenance \
    && find / -xdev -type f -perm /6000 -exec chmod a-s {} +

COPY --from=builder /build/maintenance /usr/local/bin/maintenance
COPY <<'EOF' /etc/maintenance/job.conf
# Local maintenance job definition
service_user=root
task=/opt/maintenance/tasks/backup.sh
log=/var/log/maintenance/backup.log
EOF
COPY <<'EOF' /opt/maintenance/tasks/backup.sh
#!/bin/bash
# Daily backup inventory task. Invoked by the local maintenance runner.
set -eu
date -Is >> /var/log/maintenance/backup.log
printf '%s\n' 'Backup inventory completed.'
EOF
COPY entrypoint.sh /usr/local/sbin/decoy-entrypoint
RUN chown root:root /usr/local/bin/maintenance /etc/maintenance/job.conf \
    && chmod 4755 /usr/local/bin/maintenance \
    && chmod 0644 /etc/maintenance/job.conf \
    && chown root:lowpriv /opt/maintenance/tasks/backup.sh \
    && chmod 0664 /opt/maintenance/tasks/backup.sh \
    && chmod 0755 /usr/local/sbin/decoy-entrypoint \
    && sed -i 's/\r$//' /usr/local/sbin/decoy-entrypoint \
       /opt/maintenance/tasks/backup.sh /etc/maintenance/job.conf

WORKDIR /home/lowpriv
ENTRYPOINT ["/usr/local/sbin/decoy-entrypoint"]
