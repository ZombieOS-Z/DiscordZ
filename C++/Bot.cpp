#include "Headers/Bot.h"
#include <zsharp_c.h>
#include <Python.h>
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <delayimp.h>
#include <filesystem>
#include <mutex>
#include <string>
#include <cstdlib>

namespace fs = std::filesystem;
static std::recursive_mutex botMutex;
static thread_local std::string botError;
static HMODULE pythonLibrary = nullptr;
static DLL_DIRECTORY_COOKIE pythonDirectory = nullptr;
static fs::path pythonRoot, moduleRoot;
static bool cleanupRegistered = false;
extern "C" const char* DiscordZ_BotError() { return botError.c_str(); }

static bool unpackBundledRuntime(const fs::path& directory) {
    const auto archive = directory / "python-runtime.tar.gz";
    if (!fs::exists(archive)) return false;
    std::wstring command = L"tar.exe -xzf \"" + archive.wstring() + L"\" -C \"" + directory.wstring() + L"\"";
    STARTUPINFOW startup = {}; startup.cb = sizeof(startup);
    PROCESS_INFORMATION process = {};
    if (!CreateProcessW(nullptr, command.data(), nullptr, nullptr, FALSE,
                        CREATE_NO_WINDOW, nullptr, directory.c_str(), &startup, &process)) return false;
    DWORD result = 1;
    if (WaitForSingleObject(process.hProcess, 60000) == WAIT_OBJECT_0)
        GetExitCodeProcess(process.hProcess, &result);
    else { TerminateProcess(process.hProcess, 1); WaitForSingleObject(process.hProcess, 2000); }
    CloseHandle(process.hThread); CloseHandle(process.hProcess);
    return result == 0;
}

static FARPROC WINAPI pythonDelayHook(unsigned notification, PDelayLoadInfo info) {
    if (notification == dliNotePreLoadLibrary && _stricmp(info->szDll, "python313.dll") == 0)
        return reinterpret_cast<FARPROC>(pythonLibrary);
    return nullptr;
}
extern "C" const PfnDliHook __pfnDliNotifyHook2 = pythonDelayHook;

static void capturePythonError() {
    PyObject *type = nullptr, *value = nullptr, *trace = nullptr;
    PyErr_Fetch(&type, &value, &trace);
    PyErr_NormalizeException(&type, &value, &trace);
    PyObject* message = value ? PyObject_Str(value) : nullptr;
    const char* text = message ? PyUnicode_AsUTF8(message) : nullptr;
    botError = text ? text : "Python bot operation failed";
    Py_XDECREF(message); Py_XDECREF(type); Py_XDECREF(value); Py_XDECREF(trace);
    PyErr_Clear();
}

static bool initializePython() {
    if (!pythonLibrary) {
        wchar_t executable[32768], module[32768]; HMODULE ownModule = nullptr;
        if (!GetModuleFileNameW(nullptr, executable, 32768) ||
            !GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                               reinterpret_cast<LPCWSTR>(&DiscordZ_BotLogin), &ownModule) ||
            !GetModuleFileNameW(ownModule, module, 32768)) {
            botError = "Could not locate ZVM or DiscordZ"; return false;
        }
        moduleRoot = fs::path(module).parent_path().parent_path();
        pythonRoot = fs::path(executable).parent_path() / "python";
        if (fs::path(executable).filename() == L"python.exe") pythonRoot = fs::path(executable).parent_path();
        if (!fs::exists(pythonRoot / "python313.dll"))
            unpackBundledRuntime(fs::path(executable).parent_path());
        if (!fs::exists(pythonRoot / "python313.dll") || !fs::exists(pythonRoot / "Lib" / "encodings")) {
            botError = "ZVM needs its complete Python 3.13 runtime in bin/python. Run Build.ps1 -ZVM <zsharp.exe>.";
            return false;
        }
        pythonDirectory = AddDllDirectory(pythonRoot.c_str());
        pythonLibrary = LoadLibraryExW((pythonRoot / "python313.dll").c_str(), nullptr,
            LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
        if (!pythonDirectory || !pythonLibrary) { botError = "Could not load ZVM's Python 3.13 DLL"; return false; }
    }
    if (!Py_IsInitialized()) {
        PyConfig config; PyConfig_InitIsolatedConfig(&config);
        config.install_signal_handlers = 0; config.parse_argv = 0;
        PyStatus status = PyConfig_SetString(&config, &config.home, pythonRoot.c_str());
        if (!PyStatus_Exception(status)) status = PyConfig_SetString(&config, &config.program_name, (pythonRoot / "python.exe").c_str());
        if (!PyStatus_Exception(status)) status = Py_InitializeFromConfig(&config);
        if (PyStatus_Exception(status)) {
            botError = status.err_msg ? status.err_msg : "Python initialization failed";
            PyConfig_Clear(&config); return false;
        }
        PyConfig_Clear(&config);
        PyEval_SaveThread(); // Release the GIL between native calls.
    }
    if (!cleanupRegistered) {
        std::atexit([] { DiscordZ_BotShutdown(); }); cleanupRegistered = true;
    }
    return true;
}

static PyObject* importBot() {
    PyObject* paths = PySys_GetObject("path");
    for (const auto& path : {moduleRoot / "Python", moduleRoot / "Python" / "vendor"}) {
        PyObject* value = PyUnicode_FromWideChar(path.c_str(), -1);
        int present = value ? PySequence_Contains(paths, value) : -1;
        if (present < 0 || (!present && PyList_Insert(paths, 0, value) != 0)) { Py_XDECREF(value); return nullptr; }
        Py_DECREF(value);
    }
    const char* name = "_discordz_bot";
    PyObject* cached = PyImport_GetModuleDict();
    PyObject* existing = PyDict_GetItemString(cached, name);
    if (existing) { Py_INCREF(existing); return existing; }
    PyObject* util = PyImport_ImportModule("importlib.util");
    PyObject* file = PyUnicode_FromWideChar((moduleRoot / "Python" / "Bot.py").c_str(), -1);
    PyObject* spec = util && file ? PyObject_CallMethod(util, "spec_from_file_location", "sO", name, file) : nullptr;
    PyObject* loaded = spec ? PyObject_CallMethod(util, "module_from_spec", "O", spec) : nullptr;
    PyObject* loader = spec ? PyObject_GetAttrString(spec, "loader") : nullptr;
    PyObject* executed = nullptr;
    if (loaded && loader && PyDict_SetItemString(cached, name, loaded) == 0)
        executed = PyObject_CallMethod(loader, "exec_module", "O", loaded);
    if (!executed) {
        if (loaded) {
            PyObject *type = nullptr, *value = nullptr, *trace = nullptr;
            PyErr_Fetch(&type, &value, &trace);
            PyDict_DelItemString(cached, name);
            PyErr_Restore(type, value, trace);
        }
        Py_XDECREF(loaded); loaded = nullptr;
    }
    Py_XDECREF(executed); Py_XDECREF(loader); Py_XDECREF(spec); Py_XDECREF(file); Py_XDECREF(util);
    return loaded;
}

static int callBot(const char* method, const char* first = nullptr, const char* second = nullptr, const char* third = nullptr) {
    std::lock_guard<std::recursive_mutex> lock(botMutex); botError.clear();
    if (!initializePython()) return 0;
    PyGILState_STATE gil = PyGILState_Ensure();
    PyObject* module = importBot(); PyObject* result = nullptr;
    if (module) {
        if (third) result = PyObject_CallMethod(module, method, "sss", first, second, third);
        else if (first) result = PyObject_CallMethod(module, method, "s", first);
        else result = PyObject_CallMethod(module, method, nullptr);
    }
    int success = result ? PyObject_IsTrue(result) : 0;
    if (!result || success < 0) { capturePythonError(); success = 0; }
    else if (!success) botError = "Python bot operation returned failure";
    Py_XDECREF(result); Py_XDECREF(module); PyGILState_Release(gil);
    return success;
}

int DiscordZ_BotLogin(const char* token) {
    if (!token || !*token) { botError = "Bot token is empty"; return 0; }
    return callBot("login", token);
}
int DiscordZ_BotShutdown() {
    std::lock_guard<std::recursive_mutex> lock(botMutex);
    if (!pythonLibrary || !Py_IsInitialized()) return 1;
    return callBot("shutdown");
}
int DiscordZ_BotStatus(const char* status, const char* activity, const char* details) {
    if (!status || !activity || !details) { botError = "Status arguments cannot be null"; return 0; }
    return callBot("set_status", status, activity, details);
}
extern "C" int DiscordZ_BotSelfTest() { return callBot("self_test"); }
extern "C" int DiscordZ_PythonReady() {
    std::lock_guard<std::recursive_mutex> lock(botMutex);
    return pythonLibrary != nullptr && Py_IsInitialized();
}

// All Python access, including commands and webhooks, uses the selected ZVM's
// interpreter and the same GIL/initialization path as the bot.
extern "C" int DiscordZ_PythonCall(const char* moduleName, const char* method,
    const ZSharpCValue* values, size_t count, ZSharpCValue* result) {
    static thread_local std::string returned;
    std::lock_guard<std::recursive_mutex> lock(botMutex);
    botError.clear();
    if (!initializePython()) return 0;
    PyGILState_STATE gil = PyGILState_Ensure();
    PyObject* bot = importBot();
    PyObject* module = bot ? (strcmp(moduleName, "Bot") == 0 ? Py_NewRef(bot) : PyImport_ImportModule(moduleName)) : nullptr;
    PyObject* callable = module ? PyObject_GetAttrString(module, method) : nullptr;
    PyObject* arguments = PyTuple_New(count);
    bool valid = arguments != nullptr;
    for (size_t i = 0; valid && i < count; i++) {
        PyObject* value = values[i].type == ZSHARP_C_TEXT ? PyUnicode_FromString(values[i].text ? values[i].text : "") :
            values[i].type == ZSHARP_C_NUMBER ? PyFloat_FromDouble(values[i].number) :
            values[i].type == ZSHARP_C_STATUS ? PyBool_FromLong(values[i].number != 0) : Py_BuildValue("");
        if (!value) valid = false;
        else if (PyTuple_SetItem(arguments, i, value) != 0) valid = false;
    }
    PyObject* value = callable && valid ? PyObject_CallObject(callable, arguments) : nullptr;
    int ok = value != nullptr;
    PyObject* valueType = value ? PyObject_Type(value) : nullptr;
    PyObject* typeNameObject = valueType ? PyObject_GetAttrString(valueType, "__name__") : nullptr;
    const char* typeName = typeNameObject ? PyUnicode_AsUTF8(typeNameObject) : "";
    if (value && typeName && !strcmp(typeName, "str")) {
        const char* text = PyUnicode_AsUTF8(value);
        if (text) { returned = text; result->type = ZSHARP_C_TEXT; result->text = returned.c_str(); }
        else ok = 0;
    } else if (value && typeName && !strcmp(typeName, "bool")) { result->type = ZSHARP_C_STATUS; result->number = PyObject_IsTrue(value); }
    else if (value && typeName && (!strcmp(typeName, "int") || !strcmp(typeName, "float"))) {
        result->type = ZSHARP_C_NUMBER; result->number = PyFloat_AsDouble(value); if (PyErr_Occurred()) ok = 0;
    } else if (value && typeName && !strcmp(typeName, "NoneType")) result->type = ZSHARP_C_NULL;
    else if (value) { botError = "Unsupported Python callback result"; ok = 0; }
    if (!ok && PyErr_Occurred()) capturePythonError();
    Py_XDECREF(typeNameObject); Py_XDECREF(valueType);
    Py_XDECREF(value); Py_XDECREF(arguments); Py_XDECREF(callable); Py_XDECREF(module); Py_XDECREF(bot);
    PyGILState_Release(gil);
    return ok;
}
