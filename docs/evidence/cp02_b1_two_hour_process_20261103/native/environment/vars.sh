#!/bin/sh
#
# Copyright Intel Corporation.
# 
# This software and the related documents are Intel copyrighted materials, and
# your use of them is governed by the express license under which they were
# provided to you (License). Unless the License provides otherwise, you may
# not use, modify, copy, publish, distribute, disclose or transmit this
# software or the related documents without Intel's prior written permission.
# 
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the
# License.
#
# shellcheck shell=sh

get_script_path() (
    script="$1"
    while [ -L "$script" ] ; do
        script_dir=$(command dirname -- "$script")
        script_dir=$(cd "$script_dir" && command pwd -P)
        script="$(readlink "$script")"
        case $script in
            (/*) ;;
            (*) script="$script_dir/$script" ;;
        esac
    done
    script_dir=$(command dirname -- "$script")
    script_dir=$(cd "$script_dir" && command pwd -P)
    printf "%s" "$script_dir"
)

_vars_get_proc_name() {
    if [ -n "${ZSH_VERSION:-}" ] ; then
        script="$(ps -p "$$" -o comm=)"
    else
        script="$1"
    while [ -L "$script" ] ; do
        script="$(readlink "$script")"
    done
    fi
    basename -- "$script"
}

_vars_this_script_name="vars.sh"
if [ "$_vars_this_script_name" = "$(_vars_get_proc_name "$0")" ] ; then
    echo "   ERROR: Incorrect usage: this script must be sourced."
    echo "   Usage: . path/to/${_vars_this_script_name}"
    # shellcheck disable=SC2317
    return 255 2>/dev/null || exit 255
fi


prepend_path() (
    path_to_add="$1"
    path_is_now="$2"

    if [ "" = "${path_is_now}" ]; then   # avoid dangling ":"
        printf "%s" "${path_to_add}"
    else
        printf "%s" "${path_to_add}:${path_is_now}"
    fi
)

vars_script_name=""
vars_script_shell="$(ps -p "$$" -o comm=)"

if [ -n "${ZSH_VERSION:-}" ] && [ -n "${ZSH_EVAL_CONTEXT:-}" ] ; then     # zsh 5.x and later
    # shellcheck disable=2249
    case $ZSH_EVAL_CONTEXT in (*:file*) vars_script_name="${(%):-%x}" ;; esac ;
elif [ -n "${KSH_VERSION:-}" ] ; then                                     # ksh, mksh or lksh
    if [ "$(set | grep -Fq "KSH_VERSION=.sh.version" ; echo $?)" -eq 0 ] ; then # ksh
        vars_script_name="${.sh.file}" ;
    else
        vars_script_name="$( (echo "${.sh.file}") 2>&1 )" || : ;
        vars_script_name="$(expr "${vars_script_name:-}" : '^.*sh: \(.*\)\[[0-9]*\]:')" ;
    fi
elif [ -n "${BASH_VERSION:-}" ] ; then        # bash
    # shellcheck disable=2128
    (return 0 2>/dev/null) && vars_script_name="${BASH_SOURCE}" ;
elif [ "dash" = "$vars_script_shell" ] ; then # dash
    vars_script_name="$( (echo "${.sh.file}") 2>&1 )" || : ;
    vars_script_name="$(expr "${vars_script_name:-}" : '^.*dash: [0-9]*: \(.*\):')" ;
elif [ "sh" = "$vars_script_shell" ] ; then   # could be dash masquerading as /bin/sh
    vars_script_name="$( (echo "${.sh.file}") 2>&1 )" || : ;
    if [ "$(printf "%s" "$vars_script_name" | grep -Eq "sh: [0-9]+: .*vars\.sh: " ; echo $?)" -eq 0 ] ; then # dash as sh
        vars_script_name="$(expr "${vars_script_name:-}" : '^.*sh: [0-9]*: \(.*\):')" ;
    fi
else  # unrecognized shell or dash being sourced from within a user's script
    vars_script_name="$( (echo "${.sh.file}") 2>&1 )" || : ;
    if [ "$(printf "%s" "$vars_script_name" | grep -Eq "^.+: [0-9]+: .*vars\.sh: " ; echo $?)" -eq 0 ] ; then # dash
        vars_script_name="$(expr "${vars_script_name:-}" : '^.*: [0-9]*: \(.*\):')" ;
    else
        vars_script_name="" ;
    fi
fi

if [ "" = "$vars_script_name" ] ; then
    >&2 echo "   ERROR: Unable to proceed: possible causes listed below."
    >&2 echo "   This script must be sourced. Did you execute or source this script?" ;
    >&2 echo "   Unrecognized/unsupported shell (supported: bash, zsh, ksh, m/lksh, dash)." ;
    >&2 echo "   May fail in dash if you rename this script (assumes \"vars.sh\")." ;
    >&2 echo "   Can be caused by sourcing from ZSH version 4.x or older." ;
    # shellcheck disable=SC2317
    return 255 2>/dev/null || exit 255
fi


print_help()
{
    echo ""
    echo "Usage: vars.sh [-i_mpi_ofi_internal[=0|1]] [-i_mpi_library_kind[=debug|debug_mt|release|release_mt]]"
    echo ""
    echo "-i_mpi_ofi_internal specifies whether to use libfabric from the Intel(R) MPI Library."
    echo ""
    echo "If the arguments to the sourced script are ignored (consult docs"
    echo "for your shell) the alternative way to specify target is environment"
    echo "variable I_MPI_LIBRARY_KIND to pass"
    echo "-i_mpi_library_kind to the script."
    echo "Use variable I_MPI_OFI_LIBRARY_INTERNAL to pass -i_mpi_ofi_internal setting."
    echo ""
}

set_standalone_vars()
{
    PKG_CONFIG_PATH=$(prepend_path "${I_MPI_ROOT}/lib/pkgconfig" "${PKG_CONFIG_PATH:-}"); export PKG_CONFIG_PATH
    PATH=$(prepend_path "${I_MPI_ROOT}/bin" "${PATH:-}"); export PATH
    CLASSPATH=$(prepend_path "${I_MPI_ROOT}/share/java/mpi.jar" "${CLASSPATH:-}"); export CLASSPATH
    LIBRARY_PATH=$(prepend_path "${I_MPI_ROOT}/lib" "${LIBRARY_PATH:-}") ; export LIBRARY_PATH
    LD_LIBRARY_PATH=$(prepend_path "${I_MPI_ROOT}/lib" "${LD_LIBRARY_PATH:-}") ; export LD_LIBRARY_PATH
    C_INCLUDE_PATH=$(prepend_path "${I_MPI_ROOT}/include" "${C_INCLUDE_PATH:-}") ; export C_INCLUDE_PATH
    CPLUS_INCLUDE_PATH=$(prepend_path "${I_MPI_ROOT}/include" "${CPLUS_INCLUDE_PATH:-}") ; export CPLUS_INCLUDE_PATH
    MANPATH=$(prepend_path "${I_MPI_ROOT}/share/man" "${MANPATH:-}") ; export MANPATHN
}

if [ -z "${I_MPI_OFI_LIBRARY_INTERNAL:-}" ]
then
    i_mpi_ofi_library_internal="1"
else
    i_mpi_ofi_library_internal="${I_MPI_OFI_LIBRARY_INTERNAL}"
fi

i_mpi_library_kind="${I_MPI_LIBRARY_KIND:-}"

args=$*
for arg in $args
do
    case "$arg" in
        -i_mpi_ofi_internal|--i_mpi_ofi_internal)
            i_mpi_ofi_library_internal=1
            ;;
        -i_mpi_ofi_internal=*|--i_mpi_ofi_internal=*)
            i_mpi_ofi_library_internal="${arg#*=}"
            ;;
        -h|--help)
            print_help
            return 0
            ;;
        -i_mpi_library_kind=*|--i_mpi_library_kind=*)
            i_mpi_library_kind="${arg#*=}"
            ;;
    esac
done

# ############################################################################

# If this script is located in `etc/<component-name>/vars.sh` it must be
# _sourced_ by the top-level oneapi-vars.sh script and is not a stand-alone
# script. In this case it is assumed to be located in a 2024 layout.

# If located in `<component>/<version>/env/vars.sh` this vars.sh script is a
# stand-alone script that could be located in a 2023 or earlier layout.

# NOTE: See the oneapi-vars.sh script for a list of the top-level environment
# variables that it provides. Also, if a comoponent vars.sh script must
# augment an existing environment variable it should use the prepend_path()
# and prepend_manpath() functions.

i_mpi_work_dir=$(get_script_path "${vars_script_name:-}")

if [ "$(basename "${i_mpi_work_dir}")" = "env" ] ; then   # assume standalone
    # within this "if" reference $i_mpi_work_dir **not** $ONEAPI_ROOT (below)
    I_MPI_ROOT="$(dirname "${i_mpi_work_dir}")"
    set_standalone_vars
else

    # within this "else" reference $ONEAPI_ROOT **not** $i_mpi_work_dir (above)

    if [ -z "${SETVARS_CALL:-}" ] ; then
    >&2 echo " "
    >&2 echo ":: ERROR: This script must be sourced by oneapi-vars.sh."
    >&2 echo "   Try 'source <install-dir>/oneapi-vars.sh --help' for help."
    >&2 echo " "
    return 255
    fi

    if [ -z "${ONEAPI_ROOT:-}" ] ; then
    >&2 echo " "
    >&2 echo ":: ERROR: This script requires that the ONEAPI_ROOT env variable is set."
    >&2 echo "   Try 'source <install-dir>\oneapi-vars.sh --help' for help."
    >&2 echo " "
    return 254
    fi
    I_MPI_ROOT=${ONEAPI_ROOT}
fi


case "$i_mpi_library_kind" in
    debug|debug_mt)
        LD_LIBRARY_PATH=$(prepend_path "${I_MPI_ROOT}/lib/mpi/debug" "${LD_LIBRARY_PATH:-}") ; export LD_LIBRARY_PATH
        ;;
esac

case "$i_mpi_ofi_library_internal" in
    0|no|off|disable)
        ;;
    *)
        LD_LIBRARY_PATH=$(prepend_path "${I_MPI_ROOT}/opt/mpi/libfabric/lib" "${LD_LIBRARY_PATH:-}") ; export LD_LIBRARY_PATH
        if [ -n "$( cat /etc/*release* 2>/dev/null | grep -i "Ubuntu" )" ];
        then
            FI_PROVIDER_PATH="${I_MPI_ROOT}/opt/mpi/libfabric/lib/prov:/usr/lib/x86_64-linux-gnu/libfabric"; export FI_PROVIDER_PATH
        else
            FI_PROVIDER_PATH="${I_MPI_ROOT}/opt/mpi/libfabric/lib/prov:/usr/lib64/libfabric"; export FI_PROVIDER_PATH
        fi
        ;;
esac

unset i_mpi_work_dir
unset i_mpi_library_kind
unset i_mpi_ofi_library_internal

export I_MPI_ROOT
