/*
 * Narrow replacement for rwl_v3.c's legacy system("ncgen -o ... ...").
 *
 * The normal mode deliberately calls the platform system() function.  The
 * bound mode is enabled only by CLOUD_BAL_NCGEN_MODE=bound and executes a
 * hash-bound ncgen memfd through a hash-bound loader memfd.  The coordinator
 * must hash-bind both descriptors, inspect the loader list, and stage the
 * runtime and input tree before entering the Landlock policy.
 */

#define _GNU_SOURCE

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <signal.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

extern char **environ;

#ifndef F_GET_SEALS
#define F_GET_SEALS 1034
#endif
#ifndef F_SEAL_SEAL
#define F_SEAL_SEAL 0x0001
#endif
#ifndef F_SEAL_SHRINK
#define F_SEAL_SHRINK 0x0002
#endif
#ifndef F_SEAL_GROW
#define F_SEAL_GROW 0x0004
#endif
#ifndef F_SEAL_WRITE
#define F_SEAL_WRITE 0x0008
#endif
#ifndef SYS_close_range
#define SYS_close_range 436
#endif

#define REQUIRED_SEALS \
    (F_SEAL_WRITE | F_SEAL_GROW | F_SEAL_SHRINK | F_SEAL_SEAL)
#define BRIDGE_FD_NCGEN 3
#define BRIDGE_FD_LOADER 4
#define MAX_TOKEN PATH_MAX

typedef struct {
    char output[MAX_TOKEN];
    char cdl[MAX_TOKEN];
} ncgen_command;

static int copy_token(const char **cursor, char *destination, size_t capacity,
                      int final_token)
{
    const char *current;
    size_t length;

    current = *cursor;
    length = 0;
    if (*current == '\0') {
        return -1;
    }
    while (*current != '\0' && *current != ' ') {
        unsigned char character;

        character = (unsigned char)*current;
        if (character <= 0x20 || character == 0x7f || length + 1 >= capacity) {
            return -1;
        }
        destination[length++] = *current++;
    }
    destination[length] = '\0';
    if (final_token) {
        return *current == '\0' ? 0 : -1;
    }
    if (*current != ' ') {
        return -1;
    }
    ++current;
    if (*current == '\0' || *current == ' ') {
        return -1;
    }
    *cursor = current;
    return 0;
}

static int safe_path(const char *path)
{
    const char *cursor;

    if (path[0] != '/' || path[1] == '\0') {
        return -1;
    }
    if (strstr(path, "//") != NULL) {
        return -1;
    }
    cursor = path + 1;
    while (*cursor != '\0') {
        const char *end;
        size_t length;

        end = strchr(cursor, '/');
        if (end == NULL) {
            end = cursor + strlen(cursor);
        }
        length = (size_t)(end - cursor);
        if ((length == 1 && cursor[0] == '.') ||
            (length == 2 && cursor[0] == '.' && cursor[1] == '.')) {
            return -1;
        }
        {
            const char *character;

            for (character = cursor; character < end; ++character) {
                if (strchr("\t\r\n;|&$`'\"<>*?[](){}\\", *character) != NULL) {
                    return -1;
                }
            }
        }
        if (*end == '\0') {
            break;
        }
        cursor = end + 1;
        if (*cursor == '\0') {
            return -1;
        }
    }
    return 0;
}

static int parse_bound_command(const char *command, ncgen_command *parsed)
{
    char token[MAX_TOKEN];
    const char *cursor;

    if (command == NULL || parsed == NULL) {
        errno = EINVAL;
        return -1;
    }
    cursor = command;
    if (copy_token(&cursor, token, sizeof(token), 0) != 0 ||
        strcmp(token, "ncgen") != 0 ||
        copy_token(&cursor, token, sizeof(token), 0) != 0 ||
        strcmp(token, "-o") != 0 ||
        copy_token(&cursor, parsed->output, sizeof(parsed->output), 0) != 0 ||
        copy_token(&cursor, parsed->cdl, sizeof(parsed->cdl), 1) != 0 ||
        safe_path(parsed->output) != 0 || safe_path(parsed->cdl) != 0) {
        errno = EINVAL;
        return -1;
    }
    return 0;
}

static int parse_fd(const char *name)
{
    char *end;
    long value;

    if (name == NULL || *name == '\0') {
        errno = EINVAL;
        return -1;
    }
    errno = 0;
    value = strtol(name, &end, 10);
    if (errno != 0 || *end != '\0' || value < 0 || value > INT_MAX) {
        errno = EINVAL;
        return -1;
    }
    return (int)value;
}

static int sealed_fd(int fd)
{
    int seals;

    seals = fcntl(fd, F_GET_SEALS);
    if (seals < 0 || (seals & REQUIRED_SEALS) != REQUIRED_SEALS) {
        errno = EINVAL;
        return -1;
    }
    return 0;
}

static int canonical_runtime(const char *value, char **canonical)
{
    struct stat metadata;
    char *resolved;

    if (value == NULL || value[0] != '/' || strchr(value, ':') != NULL) {
        errno = EINVAL;
        return -1;
    }
    resolved = realpath(value, NULL);
    if (resolved == NULL || strcmp(resolved, value) != 0 ||
        stat(resolved, &metadata) != 0 || !S_ISDIR(metadata.st_mode)) {
        free(resolved);
        errno = EINVAL;
        return -1;
    }
    *canonical = resolved;
    return 0;
}

static int validate_inputs(const ncgen_command *command, int *cdl_fd)
{
    struct stat cdl_metadata;
    struct stat output_metadata;
    int fd;

    fd = open(command->cdl, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) {
        return -1;
    }
    if (fstat(fd, &cdl_metadata) != 0 || !S_ISREG(cdl_metadata.st_mode) ||
        cdl_metadata.st_nlink != 1) {
        close(fd);
        errno = EINVAL;
        return -1;
    }
    if (lstat(command->output, &output_metadata) == 0) {
        if (!S_ISREG(output_metadata.st_mode) || output_metadata.st_nlink != 1 ||
            (output_metadata.st_dev == cdl_metadata.st_dev &&
             output_metadata.st_ino == cdl_metadata.st_ino)) {
            close(fd);
            errno = EINVAL;
            return -1;
        }
    } else if (errno != ENOENT) {
        close(fd);
        return -1;
    }
    *cdl_fd = fd;
    return 0;
}

static int clear_cloexec(int fd)
{
    int flags;

    flags = fcntl(fd, F_GETFD);
    if (flags < 0 || fcntl(fd, F_SETFD, flags & ~FD_CLOEXEC) < 0) {
        return -1;
    }
    return 0;
}

static int close_child_descriptors(void)
{
    long maximum;
    int fd;

    if (syscall(SYS_close_range, (unsigned int)(BRIDGE_FD_LOADER + 1),
                ~0U, 0U) == 0) {
        return 0;
    }
    if (errno != ENOSYS && errno != EINVAL) {
        return -1;
    }
    maximum = sysconf(_SC_OPEN_MAX);
    if (maximum < BRIDGE_FD_LOADER + 1) {
        maximum = 65536;
    }
    for (fd = BRIDGE_FD_LOADER + 1; fd < maximum; ++fd) {
        close(fd);
    }
    return 0;
}

static int blocked_environment_name(const char *entry)
{
    return strncmp(entry, "LD_", 3) == 0 ||
           strncmp(entry, "GCONV_PATH=", 11) == 0 ||
           strncmp(entry, "LOCPATH=", 8) == 0 ||
           strncmp(entry, "GLIBC_TUNABLES=", 15) == 0 ||
           strncmp(entry, "CLOUD_BAL_NCGEN_", 17) == 0;
}

static char **bound_environment(const char *runtime, char **library_path_out)
{
    char **environment;
    char *library_path;
    size_t count;
    size_t index;
    size_t kept;

    count = 0;
    while (environ[count] != NULL) {
        ++count;
    }
    environment = (char **)calloc(count + 2, sizeof(char *));
    if (environment == NULL) {
        return NULL;
    }
    kept = 0;
    for (index = 0; index < count; ++index) {
        if (!blocked_environment_name(environ[index])) {
            environment[kept++] = environ[index];
        }
    }
    library_path = (char *)malloc(strlen(runtime) + 18);
    if (library_path == NULL) {
        free(environment);
        return NULL;
    }
    sprintf(library_path, "LD_LIBRARY_PATH=%s", runtime);
    environment[kept++] = library_path;
    environment[kept] = NULL;
    *library_path_out = library_path;
    return environment;
}

static int exec_bound_ncgen(const ncgen_command *command, int ncgen_fd,
                            int loader_fd, const char *runtime)
{
    char loader_path[64];
    char ncgen_path[64];
    char **environment;
    char *library_path;
    char *arguments[11];
    int temporary_ncgen;
    int temporary_loader;

    temporary_ncgen = fcntl(ncgen_fd, F_DUPFD, 100);
    temporary_loader = fcntl(loader_fd, F_DUPFD, 100);
    if (temporary_ncgen < 0 || temporary_loader < 0 ||
        clear_cloexec(temporary_ncgen) != 0 ||
        clear_cloexec(temporary_loader) != 0 ||
        dup2(temporary_ncgen, BRIDGE_FD_NCGEN) < 0 ||
        dup2(temporary_loader, BRIDGE_FD_LOADER) < 0) {
        if (temporary_ncgen >= 0) {
            close(temporary_ncgen);
        }
        if (temporary_loader >= 0) {
            close(temporary_loader);
        }
        return -1;
    }
    close(temporary_ncgen);
    close(temporary_loader);
    if (close_child_descriptors() != 0 ||
        snprintf(loader_path, sizeof(loader_path), "/proc/self/fd/%d",
                 BRIDGE_FD_LOADER) >= (int)sizeof(loader_path) ||
        snprintf(ncgen_path, sizeof(ncgen_path), "/proc/self/fd/%d",
                 BRIDGE_FD_NCGEN) >= (int)sizeof(ncgen_path)) {
        return -1;
    }
    environment = bound_environment(runtime, &library_path);
    if (environment == NULL) {
        errno = ENOMEM;
        return -1;
    }
    arguments[0] = loader_path;
    arguments[1] = "--inhibit-cache";
    arguments[2] = "--library-path";
    arguments[3] = (char *)runtime;
    arguments[4] = "--argv0";
    arguments[5] = "ncgen";
    arguments[6] = ncgen_path;
    arguments[7] = "-o";
    arguments[8] = (char *)command->output;
    arguments[9] = (char *)command->cdl;
    arguments[10] = NULL;
    execve(loader_path, arguments, environment);
    free(library_path);
    free(environment);
    return -1;
}

static int run_bound_ncgen(const char *command)
{
    ncgen_command parsed;
    char *runtime;
    const char *mode;
    int cdl_fd;
    int loader_fd;
    int ncgen_fd;
    int status;
    pid_t child;
    pid_t waited;

    mode = getenv("CLOUD_BAL_NCGEN_MODE");
    if (mode == NULL) {
#ifdef system
#undef system
#endif
        return system(command);
    }
    if (strcmp(mode, "bound") != 0) {
        errno = EINVAL;
        return -1;
    }
    if (parse_bound_command(command, &parsed) != 0 ||
        canonical_runtime(getenv("CLOUD_BAL_NCGEN_RUNTIME"), &runtime) != 0) {
        return -1;
    }
    ncgen_fd = parse_fd(getenv("CLOUD_BAL_NCGEN_FD"));
    loader_fd = parse_fd(getenv("CLOUD_BAL_NCGEN_LOADER_FD"));
    if (ncgen_fd < 0 || loader_fd < 0 || ncgen_fd == loader_fd ||
        sealed_fd(ncgen_fd) != 0 || sealed_fd(loader_fd) != 0 ||
        validate_inputs(&parsed, &cdl_fd) != 0) {
        free(runtime);
        return -1;
    }
    close(cdl_fd);
    child = fork();
    if (child < 0) {
        free(runtime);
        return -1;
    }
    if (child == 0) {
        if (exec_bound_ncgen(&parsed, ncgen_fd, loader_fd, runtime) != 0) {
            _exit(127);
        }
    }
    free(runtime);
    do {
        waited = waitpid(child, &status, 0);
    } while (waited < 0 && errno == EINTR);
    if (waited < 0) {
        return -1;
    }
    return status;
}

int cloud_bal_ncgen_system(const char *command)
{
    return run_bound_ncgen(command);
}
