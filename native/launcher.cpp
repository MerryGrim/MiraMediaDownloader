// SPDX-License-Identifier: GPL-2.0-or-later
// Tiny Windows front door: paint immediately, then start the isolated Python core.
#include <windows.h>
#include <windowsx.h>
#include <winver.h>
#include <shellapi.h>
#include <shobjidl.h>
#include <bcrypt.h>
#include <dwmapi.h>
#include <algorithm>
#include <objidl.h>
#include <gdiplus.h>
#include <cstdio>
#include <cwchar>
#include <memory>
#include <string>
#include <vector>
#include "vc_runtime_requirement.h"

#define MIRA_WIDEN_IMPL(value) L##value
#define MIRA_WIDEN(value) MIRA_WIDEN_IMPL(value)

namespace {
constexpr wchar_t kWindowClass[] = L"MiraNativeStartup";
constexpr wchar_t kEventVariable[] = L"MIRA_STARTUP_EVENT";
constexpr DWORD kStartupTimeout = 60000;
constexpr int kIconResource = 101;
constexpr int kArtworkResource = 201;
constexpr wchar_t kAppUserModelId[] = L"Mira.MiraMediaDownloader";

bool RuntimeVersionIsSupported(DWORD ms, DWORD ls) {
    constexpr DWORD requiredMs = (static_cast<DWORD>(MIRA_VC_RUNTIME_MAJOR) << 16) | MIRA_VC_RUNTIME_MINOR;
    constexpr DWORD requiredLs = (static_cast<DWORD>(MIRA_VC_RUNTIME_BUILD) << 16) | MIRA_VC_RUNTIME_REVISION;
    return ms > requiredMs || (ms == requiredMs && ls >= requiredLs);
}

struct RuntimeFile {
    const wchar_t* name;
    DWORD ms = 0, ls = 0;
    bool found = false;
};

struct RuntimeRequirement {
    bool satisfied = true;
    std::vector<RuntimeFile> files{
        {L"msvcp140.dll"}, {L"msvcp140_1.dll"}, {L"msvcp140_2.dll"},
        {L"vcruntime140.dll"}, {L"vcruntime140_1.dll"}
    };
};

RuntimeRequirement CheckSystemRuntime() {
    RuntimeRequirement result;
    // Never load or inspect a runtime supplied by the current directory, PATH,
    // an unrelated application or a user profile. This launcher is x64 /MT.
    wchar_t directory[32768]{};
    UINT length = GetSystemDirectoryW(directory, ARRAYSIZE(directory));
    HMODULE version = LoadLibraryExW(L"version.dll", nullptr, LOAD_LIBRARY_SEARCH_SYSTEM32);
    using SizeFunction = DWORD (WINAPI*)(LPCWSTR, LPDWORD);
    using InfoFunction = BOOL (WINAPI*)(LPCWSTR, DWORD, DWORD, LPVOID);
    using QueryFunction = BOOL (WINAPI*)(LPCVOID, LPCWSTR, LPVOID*, PUINT);
    auto sizeOf = version ? reinterpret_cast<SizeFunction>(GetProcAddress(version, "GetFileVersionInfoSizeW")) : nullptr;
    auto info = version ? reinterpret_cast<InfoFunction>(GetProcAddress(version, "GetFileVersionInfoW")) : nullptr;
    auto query = version ? reinterpret_cast<QueryFunction>(GetProcAddress(version, "VerQueryValueW")) : nullptr;
    for (auto& file : result.files) {
        if (length && length < ARRAYSIZE(directory) && sizeOf && info && query) {
            std::wstring path = std::wstring(directory, length) + L"\\" + file.name;
            DWORD ignored = 0, bytes = sizeOf(path.c_str(), &ignored);
            if (bytes && bytes <= 1024 * 1024) {
                std::vector<BYTE> data(bytes);
                VS_FIXEDFILEINFO* fixed = nullptr;
                UINT fixedBytes = 0;
                if (info(path.c_str(), 0, bytes, data.data()) &&
                    query(data.data(), L"\\", reinterpret_cast<LPVOID*>(&fixed), &fixedBytes) &&
                    fixed && fixedBytes >= sizeof(VS_FIXEDFILEINFO) && fixed->dwSignature == 0xFEEF04BD) {
                    file.found = true;
                    file.ms = fixed->dwFileVersionMS;
                    file.ls = fixed->dwFileVersionLS;
                }
            }
        }
        if (!file.found || !RuntimeVersionIsSupported(file.ms, file.ls)) result.satisfied = false;
    }
    if (version) FreeLibrary(version);
    return result;
}

void WriteBytes(DWORD stream, const std::string& text) {
    HANDLE handle = GetStdHandle(stream);
    if (handle && handle != INVALID_HANDLE_VALUE) {
        DWORD written = 0;
        WriteFile(handle, text.data(), static_cast<DWORD>(text.size()), &written, nullptr);
    }
}

void WriteRuntimeDiagnostic(const RuntimeRequirement& runtime) {
    std::string text = "{\"satisfied\":" + std::string(runtime.satisfied ? "true" : "false") +
        ",\"minimum\":\"" MIRA_VC_RUNTIME_MIN_VERSION "\",\"source\":\"System32\",\"files\":[";
    bool first = true;
    for (const auto& file : runtime.files) {
        if (!first) text += ',';
        first = false;
        std::string name;
        for (const wchar_t* value = file.name; *value; ++value) name += static_cast<char>(*value);
        text += "{\"name\":\"" + name + "\",\"found\":" + (file.found ? "true" : "false") +
            ",\"supported\":" + (file.found && RuntimeVersionIsSupported(file.ms, file.ls) ? "true" : "false") +
            ",\"version\":\"" + std::to_string(HIWORD(file.ms)) + "." + std::to_string(LOWORD(file.ms)) +
            "." + std::to_string(HIWORD(file.ls)) + "." + std::to_string(LOWORD(file.ls)) + "\"}";
    }
    WriteBytes(STD_OUTPUT_HANDLE, text + "]}\n");
}

bool RuntimeDiagnosticRequested() {
    int count = 0;
    LPWSTR* arguments = CommandLineToArgvW(GetCommandLineW(), &count);
    if (!arguments) return false;
    bool result = false;
    for (int index = 1; index < count; ++index)
        if (wcscmp(arguments[index], L"--check-runtime") == 0) result = true;
    LocalFree(arguments);
    return result;
}

struct Handle {
    HANDLE value = nullptr;
    explicit Handle(HANDLE handle = nullptr) : value(handle) {}
    ~Handle() { if (value && value != INVALID_HANDLE_VALUE) CloseHandle(value); }
    Handle(const Handle&) = delete;
    Handle& operator=(const Handle&) = delete;
    void reset(HANDLE handle = nullptr) {
        if (value && value != INVALID_HANDLE_VALUE) CloseHandle(value);
        value = handle;
    }
};

// Decode the existing installer artwork once. The stream stays alive for the
// entire GDI+ image lifetime; no temporary files or extra bundled DLLs are used.
class Artwork {
    ULONG_PTR token_ = 0;
    IStream* stream_ = nullptr;
    std::unique_ptr<Gdiplus::Image> image_;
public:
    ~Artwork() { clear(); }
    void clear() {
        image_.reset();
        if (stream_) { stream_->Release(); stream_ = nullptr; }
        if (token_) { Gdiplus::GdiplusShutdown(token_); token_ = 0; }
    }
    void load(HINSTANCE instance) {
        if (token_) return;
        Gdiplus::GdiplusStartupInput input;
        if (Gdiplus::GdiplusStartup(&token_, &input, nullptr) != Gdiplus::Ok) { token_ = 0; return; }
        HRSRC resource = FindResourceW(instance, MAKEINTRESOURCEW(kArtworkResource), RT_RCDATA);
        if (!resource) return;
        DWORD size = SizeofResource(instance, resource);
        const void* data = LockResource(LoadResource(instance, resource));
        if (!size || !data) return;
        HGLOBAL memory = GlobalAlloc(GMEM_MOVEABLE, size);
        if (!memory) return;
        void* target = GlobalLock(memory);
        if (!target) { GlobalFree(memory); return; }
        CopyMemory(target, data, size);
        GlobalUnlock(memory);
        if (FAILED(CreateStreamOnHGlobal(memory, TRUE, &stream_))) { GlobalFree(memory); return; }
        image_.reset(Gdiplus::Image::FromStream(stream_, FALSE));
        if (!image_ || image_->GetLastStatus() != Gdiplus::Ok || !image_->GetWidth() || !image_->GetHeight())
            image_.reset();
    }
    void draw(HDC buffer, const RECT& card, int radius) const {
        using namespace Gdiplus;
        Graphics graphics(buffer);
        graphics.SetSmoothingMode(SmoothingModeAntiAlias);
        GraphicsPath path;
        REAL x = static_cast<REAL>(card.left), y = static_cast<REAL>(card.top);
        REAL width = static_cast<REAL>(card.right - card.left), height = static_cast<REAL>(card.bottom - card.top);
        REAL diameter = static_cast<REAL>(radius * 2);
        path.AddArc(x, y, diameter, diameter, 180.0F, 90.0F);
        path.AddArc(x + width - diameter, y, diameter, diameter, 270.0F, 90.0F);
        path.AddArc(x + width - diameter, y + height - diameter, diameter, diameter, 0.0F, 90.0F);
        path.AddArc(x, y + height - diameter, diameter, diameter, 90.0F, 90.0F);
        path.CloseFigure();
        SolidBrush paper(Color(255, 255, 250, 240));
        graphics.FillPath(&paper, &path);
        if (!image_) return;
        graphics.SetClip(&path);
        graphics.SetInterpolationMode(InterpolationModeHighQualityBicubic);
        graphics.SetPixelOffsetMode(PixelOffsetModeHighQuality);
        // The portrait's large empty margins are excluded only while drawing.
        // Keep the complete cloud face, photos, folder and surrounding leaves.
        REAL sourceWidth = static_cast<REAL>(image_->GetWidth());
        REAL sourceTop = static_cast<REAL>(image_->GetHeight()) * 0.245F;
        REAL sourceHeight = static_cast<REAL>(image_->GetHeight()) * 0.490F;
        REAL scale = std::min(width / sourceWidth, height / sourceHeight);
        REAL drawnWidth = sourceWidth * scale, drawnHeight = sourceHeight * scale;
        RectF destination(x + (width - drawnWidth) / 2.0F, y + (height - drawnHeight) / 2.0F, drawnWidth, drawnHeight);
        graphics.DrawImage(image_.get(), destination, 0.0F, sourceTop, sourceWidth, sourceHeight, UnitPixel);
    }
};

std::wstring Environment(const wchar_t* name) {
    DWORD length = GetEnvironmentVariableW(name, nullptr, 0);
    if (!length || length > 32768) return {};
    std::vector<wchar_t> value(length);
    DWORD received = GetEnvironmentVariableW(name, value.data(), length);
    return received && received < length ? std::wstring(value.data(), received) : std::wstring();
}

std::wstring Preference(const wchar_t* overrideName, const wchar_t* key, const wchar_t* fallback) {
    std::wstring overrideValue = Environment(overrideName);
    if (!overrideValue.empty()) return overrideValue;
    // Only these two non-sensitive appearance values are read. Never enumerate
    // preferences, browser profiles, account data or collection locations.
    wchar_t value[32]{};
    DWORD bytes = sizeof(value);
    if (RegGetValueW(HKEY_CURRENT_USER, L"Software\\Mira\\MiraMediaDownloader", key,
                    RRF_RT_REG_SZ, nullptr, value, &bytes) == ERROR_SUCCESS) return value;
    return fallback;
}

struct State {
    HWND window = nullptr;
    HANDLE job = nullptr;
    HANDLE process = nullptr;
    ULONGLONG started = GetTickCount64();
    long long firstPaint = -1, spawned = -1, ready = -1, exited = -1;
    DWORD processId = 0, exitCode = 0, timeout = kStartupTimeout;
    bool dark = false, cancelled = false, timedOut = false;
    bool closeHover = false, closePressed = false;
    std::wstring language = L"ru";
    const char* reason = "starting";
    Handle trace;
    Artwork artwork;

    long long elapsed() const { return static_cast<long long>(GetTickCount64() - started); }
    const wchar_t* subtitle() const {
        if (language == L"en") return L"Preparing the interface";
        if (language == L"zh_CN") return L"正在准备界面";
        return L"Подготавливаем интерфейс";
    }
    const wchar_t* error(bool timeoutFailure) const {
        if (language == L"en") return timeoutFailure
            ? L"Mira did not open its window in time. Its startup process was stopped. Please try again."
            : L"Mira could not start. Check that the complete application is installed, then try again.";
        if (language == L"zh_CN") return timeoutFailure
            ? L"Mira 未能及时打开窗口，已停止本次启动进程。请重试。"
            : L"无法启动 Mira。请检查应用文件是否完整，然后重试。";
        return timeoutFailure
            ? L"Mira не успела открыть окно. Процесс этого запуска остановлен. Попробуйте ещё раз."
            : L"Не удалось запустить Mira. Проверьте комплектность приложения и попробуйте ещё раз.";
    }
    void writeTrace() {
        if (!trace.value || trace.value == INVALID_HANDLE_VALUE) return;
        char text[640]{};
        int length = sprintf_s(text, "{\"launcher_pid\":%lu,\"core_pid\":%lu,\"first_paint_ms\":%lld,"
            "\"core_spawn_ms\":%lld,\"ready_ms\":%lld,\"exit_ms\":%lld,\"exit_code\":%lu,"
            "\"timeout_ms\":%lu,\"dismiss_reason\":\"%s\"}\n", GetCurrentProcessId(), processId,
            firstPaint, spawned, ready, exited, exitCode, timeout, reason);
        if (length <= 0) return;
        SetFilePointer(trace.value, 0, nullptr, FILE_BEGIN);
        DWORD written = 0;
        WriteFile(trace.value, text, static_cast<DWORD>(length), &written, nullptr);
        SetEndOfFile(trace.value);
        FlushFileBuffers(trace.value);
    }
};

void Dismiss(State& state) {
    if (state.window) DestroyWindow(state.window);
}

RECT CloseBounds(HWND window) {
    RECT client{};
    GetClientRect(window, &client);
    int dpi = static_cast<int>(GetDpiForWindow(window));
    auto px = [dpi](int value) { return MulDiv(value, dpi, 96); };
    return RECT{ client.right - px(40), px(8), client.right - px(8), px(40) };
}

void Paint(State& state) {
    PAINTSTRUCT paint{};
    HDC screen = BeginPaint(state.window, &paint);
    RECT client{};
    GetClientRect(state.window, &client);
    HDC buffer = CreateCompatibleDC(screen);
    HBITMAP bitmap = CreateCompatibleBitmap(screen, client.right, client.bottom);
    HGDIOBJ oldBitmap = SelectObject(buffer, bitmap);
    COLORREF background = state.dark ? RGB(24, 28, 35) : RGB(255, 255, 255);
    COLORREF foreground = state.dark ? RGB(229, 234, 242) : RGB(37, 40, 45);
    COLORREF muted = state.dark ? RGB(158, 169, 185) : RGB(116, 124, 136);
    HBRUSH brush = CreateSolidBrush(background);
    FillRect(buffer, &client, brush);
    DeleteObject(brush);
    int dpi = static_cast<int>(GetDpiForWindow(state.window));
    auto px = [dpi](int value) { return MulDiv(value, dpi, 96); };
    RECT artworkCard{ px(16), px(16), px(212), px(224) };
    state.artwork.draw(buffer, artworkCard, px(15));
    HGDIOBJ oldBrush = nullptr, oldPen = nullptr;
    SetBkMode(buffer, TRANSPARENT);
    SetTextColor(buffer, foreground);
    HFONT titleFont = CreateFontW(-MulDiv(14, dpi, 72), 0, 0, 0, FW_SEMIBOLD, FALSE, FALSE, FALSE,
                                 DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY,
                                 DEFAULT_PITCH, L"Segoe UI");
    HGDIOBJ oldFont = SelectObject(buffer, titleFont);
    RECT title{ px(238), px(64), client.right - px(22), px(94) };
    DrawTextW(buffer, L"Mira Media Downloader", -1, &title, DT_LEFT | DT_SINGLELINE | DT_VCENTER);
    HFONT detailFont = CreateFontW(-MulDiv(10, dpi, 72), 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE,
                                  DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY,
                                  DEFAULT_PITCH, L"Segoe UI");
    SelectObject(buffer, detailFont);
    SetTextColor(buffer, muted);
    RECT detail{ px(239), px(106), client.right - px(22), px(134) };
    DrawTextW(buffer, state.subtitle(), -1, &detail, DT_LEFT | DT_SINGLELINE | DT_VCENTER);
    SelectObject(buffer, oldFont);
    DeleteObject(titleFont);
    DeleteObject(detailFont);
    unsigned active = static_cast<unsigned>((GetTickCount64() - state.started) / 280 % 3);
    for (unsigned index = 0; index < 3; ++index) {
        HBRUSH dot = CreateSolidBrush(index == active ? foreground :
            (state.dark ? RGB(65, 75, 89) : RGB(210, 216, 224)));
        oldBrush = SelectObject(buffer, dot);
        oldPen = SelectObject(buffer, GetStockObject(NULL_PEN));
        int x = px(241 + static_cast<int>(index) * 16);
        Ellipse(buffer, x, px(164), x + px(7), px(171));
        SelectObject(buffer, oldBrush);
        SelectObject(buffer, oldPen);
        DeleteObject(dot);
    }
    RECT close = CloseBounds(state.window);
    if (state.closeHover || state.closePressed) {
        HBRUSH hover = CreateSolidBrush(state.dark ? RGB(49, 57, 69) : RGB(237, 240, 244));
        oldBrush = SelectObject(buffer, hover);
        oldPen = SelectObject(buffer, GetStockObject(NULL_PEN));
        RoundRect(buffer, close.left, close.top, close.right, close.bottom, px(8), px(8));
        SelectObject(buffer, oldBrush);
        SelectObject(buffer, oldPen);
        DeleteObject(hover);
    }
    HPEN closePen = CreatePen(PS_SOLID, std::max(1, px(2)), muted);
    oldPen = SelectObject(buffer, closePen);
    int middleX = (close.left + close.right) / 2, middleY = (close.top + close.bottom) / 2;
    MoveToEx(buffer, middleX - px(5), middleY - px(5), nullptr);
    LineTo(buffer, middleX + px(5), middleY + px(5));
    MoveToEx(buffer, middleX + px(5), middleY - px(5), nullptr);
    LineTo(buffer, middleX - px(5), middleY + px(5));
    SelectObject(buffer, oldPen);
    DeleteObject(closePen);
    BitBlt(screen, 0, 0, client.right, client.bottom, buffer, 0, 0, SRCCOPY);
    SelectObject(buffer, oldBitmap);
    DeleteObject(bitmap);
    DeleteDC(buffer);
    EndPaint(state.window, &paint);
    if (state.firstPaint < 0) { state.firstPaint = state.elapsed(); state.writeTrace(); }
}

void UpdateSplashCorners(HWND window) {
    DWORD preference = IsZoomed(window) ? 1 : 2; // DONOTROUND / ROUND
    if (SUCCEEDED(DwmSetWindowAttribute(window, 33, &preference, sizeof(preference)))) {
        SetWindowRgn(window, nullptr, FALSE);
        DWORD border = 0xFFFFFFFE; // DWMWA_COLOR_NONE
        DwmSetWindowAttribute(window, 34, &border, sizeof(border));
        return;
    }
    if (IsZoomed(window)) { SetWindowRgn(window, nullptr, TRUE); return; }
    RECT rect{};
    if (!GetWindowRect(window, &rect)) return;
    int radius = MulDiv(8, static_cast<int>(GetDpiForWindow(window)), 96);
    HRGN shape = CreateRoundRectRgn(0, 0, rect.right - rect.left + 1,
        rect.bottom - rect.top + 1, radius * 2, radius * 2);
    HRGN existing = CreateRectRgn(0, 0, 0, 0);
    bool same = shape && existing && GetWindowRgn(window, existing) != ERROR && EqualRgn(shape, existing);
    if (existing) DeleteObject(existing);
    if (shape && (same || !SetWindowRgn(window, shape, TRUE))) DeleteObject(shape);
}

LRESULT CALLBACK WindowProcedure(HWND window, UINT message, WPARAM wparam, LPARAM lparam) {
    State* state = reinterpret_cast<State*>(GetWindowLongPtrW(window, GWLP_USERDATA));
    if (message == WM_NCCREATE) {
        state = static_cast<State*>(reinterpret_cast<CREATESTRUCTW*>(lparam)->lpCreateParams);
        state->window = window;
        SetWindowLongPtrW(window, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(state));
    }
    if (!state) return DefWindowProcW(window, message, wparam, lparam);
    switch (message) {
    case WM_NCCALCSIZE: return 0; // DWM frame metadata, full-size custom client.
    case WM_SIZE:
    case WM_DWMCOMPOSITIONCHANGED:
        UpdateSplashCorners(window);
        return 0;
    case WM_SYSCOMMAND:
        if ((wparam & 0xFFF0) == SC_SIZE || (wparam & 0xFFF0) == SC_MAXIMIZE) return 0;
        return DefWindowProcW(window, message, wparam, lparam);
    case WM_NCLBUTTONDBLCLK: return 0; // Startup remains a fixed-size transient.
    case WM_PAINT: Paint(*state); return 0;
    case WM_ERASEBKGND: return 1;
    case WM_TIMER: InvalidateRect(window, nullptr, FALSE); return 0;
    case WM_NCHITTEST: {
        POINT point{ GET_X_LPARAM(lparam), GET_Y_LPARAM(lparam) };
        ScreenToClient(window, &point);
        RECT close = CloseBounds(window);
        return PtInRect(&close, point) ? HTCLIENT : HTCAPTION;
    }
    case WM_MOUSEMOVE: {
        POINT point{ GET_X_LPARAM(lparam), GET_Y_LPARAM(lparam) };
        RECT close = CloseBounds(window);
        bool hover = PtInRect(&close, point) != FALSE;
        if (hover != state->closeHover) {
            state->closeHover = hover;
            InvalidateRect(window, &close, FALSE);
        }
        TRACKMOUSEEVENT tracking{ sizeof(tracking), TME_LEAVE, window, 0 };
        TrackMouseEvent(&tracking);
        return 0;
    }
    case WM_MOUSELEAVE:
        state->closeHover = false;
        InvalidateRect(window, nullptr, FALSE);
        return 0;
    case WM_LBUTTONDOWN: {
        POINT point{ GET_X_LPARAM(lparam), GET_Y_LPARAM(lparam) };
        RECT close = CloseBounds(window);
        if (PtInRect(&close, point)) {
            state->closePressed = true;
            SetCapture(window);
            InvalidateRect(window, &close, FALSE);
        }
        return 0;
    }
    case WM_LBUTTONUP: {
        POINT point{ GET_X_LPARAM(lparam), GET_Y_LPARAM(lparam) };
        RECT close = CloseBounds(window);
        bool cancel = state->closePressed && PtInRect(&close, point);
        state->closePressed = false;
        if (GetCapture() == window) ReleaseCapture();
        if (cancel) PostMessageW(window, WM_CLOSE, 0, 0);
        else InvalidateRect(window, &close, FALSE);
        return 0;
    }
    case WM_CAPTURECHANGED:
        state->closePressed = false;
        InvalidateRect(window, nullptr, FALSE);
        return 0;
    case WM_SYSKEYDOWN:
        if (wparam == VK_F4 && (lparam & (static_cast<LPARAM>(1) << 29))) {
            PostMessageW(window, WM_CLOSE, 0, 0);
            return 0;
        }
        return DefWindowProcW(window, message, wparam, lparam);
    case WM_CLOSE:
        state->cancelled = true;
        state->reason = "cancelled";
        if (state->job) TerminateJobObject(state->job, ERROR_CANCELLED);
        DestroyWindow(window);
        state->writeTrace();
        return 0;
    case WM_DESTROY:
        KillTimer(window, 1);
        state->window = nullptr;
        // All painting is over. The parent may wait for Core for hours, so
        // discard the decoded pixels, source stream and GDI+ token now.
        state->artwork.clear();
        return 0;  // Keep watching the owned core after the splash closes.
    default: return DefWindowProcW(window, message, wparam, lparam);
    }
}

bool ShowSplash(HINSTANCE instance, State& state) {
    state.artwork.load(instance);
    WNDCLASSEXW cls{};
    cls.cbSize = sizeof(cls);
    cls.lpfnWndProc = WindowProcedure;
    cls.hInstance = instance;
    UINT iconDpi = GetDpiForSystem();
    cls.hIcon = static_cast<HICON>(LoadImageW(instance, MAKEINTRESOURCEW(kIconResource), IMAGE_ICON,
        GetSystemMetricsForDpi(SM_CXICON, iconDpi), GetSystemMetricsForDpi(SM_CYICON, iconDpi), LR_SHARED));
    cls.hIconSm = static_cast<HICON>(LoadImageW(instance, MAKEINTRESOURCEW(kIconResource), IMAGE_ICON,
        GetSystemMetricsForDpi(SM_CXSMICON, iconDpi), GetSystemMetricsForDpi(SM_CYSMICON, iconDpi), LR_SHARED));
    cls.hCursor = LoadCursorW(nullptr, IDC_ARROW);
    cls.lpszClassName = kWindowClass;
    if (!RegisterClassExW(&cls) && GetLastError() != ERROR_CLASS_ALREADY_EXISTS) return false;
    POINT pointer{};
    GetCursorPos(&pointer);
    MONITORINFO monitor{ sizeof(monitor) };
    GetMonitorInfoW(MonitorFromPoint(pointer, MONITOR_DEFAULTTOPRIMARY), &monitor);
    int dpi = static_cast<int>(GetDpiForSystem());
    RECT rectangle{ 0, 0, MulDiv(560, dpi, 96), MulDiv(240, dpi, 96) };
    // Keep enough frame metadata for DWM's rounded-corner policy. NCCALCSIZE
    // removes the non-client frame, so these are the original body dimensions.
    DWORD style = WS_POPUP | WS_CAPTION | WS_THICKFRAME;
    int width = rectangle.right - rectangle.left, height = rectangle.bottom - rectangle.top;
    int left = monitor.rcWork.left + (monitor.rcWork.right - monitor.rcWork.left - width) / 2;
    int top = monitor.rcWork.top + (monitor.rcWork.bottom - monitor.rcWork.top - height) / 2;
    HWND window = CreateWindowExW(WS_EX_APPWINDOW, kWindowClass, L"Mira Media Downloader", style,
                                  left, top, width, height, nullptr, nullptr, instance, &state);
    if (!window) return false;
    // Explicit per-window handles prevent a frameless startup window from
    // falling back to Windows' generic application icon for its taskbar group.
    SendMessageW(window, WM_SETICON, ICON_BIG, reinterpret_cast<LPARAM>(cls.hIcon));
    SendMessageW(window, WM_SETICON, ICON_SMALL, reinterpret_cast<LPARAM>(cls.hIconSm));
    BOOL dark = state.dark;
    DwmSetWindowAttribute(window, 20 /* DWMWA_USE_IMMERSIVE_DARK_MODE */, &dark, sizeof(dark));
    UpdateSplashCorners(window);
    ShowWindow(window, SW_SHOWNORMAL);
    UpdateWindow(window); // First real native paint precedes starting Python.
    SetTimer(window, 1, 90, nullptr);
    return true;
}

bool IsCommandMode() {
    int count = 0;
    LPWSTR* arguments = CommandLineToArgvW(GetCommandLineW(), &count);
    if (!arguments) return false;
    const wchar_t* flags[] = { L"--worker", L"--version", L"--screenshot", L"--design-probe",
                             L"--login-probe", L"--help", L"-h" };
    bool result = false;
    for (int index = 1; index < count && !result; ++index) {
        for (const wchar_t* flag : flags) {
            size_t length = wcslen(flag);
            if (wcsncmp(arguments[index], flag, length) == 0 &&
                (arguments[index][length] == L'\0' || arguments[index][length] == L'=')) {
                result = true; break;
            }
        }
    }
    LocalFree(arguments);
    return result;
}

const wchar_t* RawArgumentTail() {
    const wchar_t* text = GetCommandLineW();
    while (*text == L' ' || *text == L'\t') ++text;
    if (*text == L'"') {
        ++text;
        while (*text && *text != L'"') ++text;
        if (*text) ++text;
    } else {
        while (*text && *text != L' ' && *text != L'\t') ++text;
    }
    return text; // Preserve every argument's original Windows quoting exactly.
}

std::wstring CreateReadyEvent(Handle& event) {
    unsigned char random[16]{};
    if (BCryptGenRandom(nullptr, random, sizeof(random), BCRYPT_USE_SYSTEM_PREFERRED_RNG) < 0) return {};
    wchar_t nonce[33]{};
    for (int index = 0; index < 16; ++index) swprintf_s(nonce + index * 2, 3, L"%02x", random[index]);
    std::wstring name = L"Local\\MiraStartup-" + std::to_wstring(GetCurrentProcessId()) + L"-" + nonce;
    event.reset(CreateEventW(nullptr, TRUE, FALSE, name.c_str()));
    if (!event.value || GetLastError() == ERROR_ALREADY_EXISTS) { event.reset(); return {}; }
    return name;
}

std::vector<wchar_t> ChildEnvironment(const std::wstring& eventName) {
    std::vector<std::wstring> rows;
    wchar_t* block = GetEnvironmentStringsW();
    if (block) {
        for (const wchar_t* item = block; *item; item += wcslen(item) + 1) {
            if (_wcsnicmp(item, L"MIRA_STARTUP_EVENT=", 19) != 0 &&
                _wcsnicmp(item, L"MIRA_STARTUP_TRACE=", 19) != 0) rows.emplace_back(item);
        }
        FreeEnvironmentStringsW(block);
    }
    if (!eventName.empty()) rows.emplace_back(std::wstring(kEventVariable) + L"=" + eventName);
    std::sort(rows.begin(), rows.end(), [](const std::wstring& left, const std::wstring& right) {
        return _wcsicmp(left.c_str(), right.c_str()) < 0;
    });
    std::vector<wchar_t> result;
    for (const auto& row : rows) { result.insert(result.end(), row.begin(), row.end()); result.push_back(L'\0'); }
    result.push_back(L'\0');
    if (rows.empty()) result.push_back(L'\0');
    return result;
}

struct ChildStartup {
    STARTUPINFOEXW info{};
    std::vector<unsigned char> attributeStorage;
    std::vector<HANDLE> inherited;
    bool attributesInitialized = false;
    ChildStartup() {
        info.StartupInfo.cb = sizeof(STARTUPINFOW);
        DWORD names[] = { STD_INPUT_HANDLE, STD_OUTPUT_HANDLE, STD_ERROR_HANDLE };
        HANDLE* destinations[] = { &info.StartupInfo.hStdInput, &info.StartupInfo.hStdOutput, &info.StartupInfo.hStdError };
        for (unsigned index = 0; index < 3; ++index) {
            HANDLE original = GetStdHandle(names[index]), duplicate = nullptr;
            if (original && original != INVALID_HANDLE_VALUE &&
                DuplicateHandle(GetCurrentProcess(), original, GetCurrentProcess(), &duplicate, 0, TRUE, DUPLICATE_SAME_ACCESS)) {
                inherited.push_back(duplicate);
                *destinations[index] = duplicate;
            }
        }
        if (!inherited.empty()) {
            info.StartupInfo.dwFlags |= STARTF_USESTDHANDLES;
            SIZE_T bytes = 0;
            InitializeProcThreadAttributeList(nullptr, 1, 0, &bytes);
            attributeStorage.resize(bytes);
            info.lpAttributeList = reinterpret_cast<LPPROC_THREAD_ATTRIBUTE_LIST>(attributeStorage.data());
            if (InitializeProcThreadAttributeList(info.lpAttributeList, 1, 0, &bytes)) {
                attributesInitialized = true;
                if (UpdateProcThreadAttribute(info.lpAttributeList, 0, PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
                                              inherited.data(), inherited.size() * sizeof(HANDLE), nullptr, nullptr))
                    info.StartupInfo.cb = sizeof(STARTUPINFOEXW);
            }
        }
    }
    bool valid() const { return inherited.empty() || info.StartupInfo.cb == sizeof(STARTUPINFOEXW); }
    ~ChildStartup() {
        if (attributesInitialized) DeleteProcThreadAttributeList(info.lpAttributeList);
        for (HANDLE handle : inherited) CloseHandle(handle);
    }
};

void ReportError(State& state, bool graphical, bool timeoutFailure, DWORD code) {
    if (graphical) {
        std::wstring body = state.error(timeoutFailure);
        body += L"\n\nWindows: " + std::to_wstring(code);
        MessageBoxW(nullptr, body.c_str(), L"Mira Media Downloader", MB_OK | MB_ICONERROR);
    } else {
        char body[120]{};
        int length = sprintf_s(body, "Mira core could not be started (Windows error %lu).\n", code);
        HANDLE error = GetStdHandle(STD_ERROR_HANDLE);
        if (error && error != INVALID_HANDLE_VALUE && length > 0) {
            DWORD written = 0;
            WriteFile(error, body, static_cast<DWORD>(length), &written, nullptr);
        }
    }
}

void ReportRuntimeRequirement(const State& state, bool graphical) {
    const wchar_t* body;
    if (state.language == L"en") body =
        L"Mira needs Microsoft Visual C++ x64 Runtime " MIRA_WIDEN(MIRA_VC_RUNTIME_MIN_VERSION) L" or newer.\n\n"
        L"Install it from Microsoft, review its license in Microsoft's installer, then open Mira again. "
        L"Mira does not include this separate Microsoft component.\n\nOpen the official Microsoft download page?";
    else if (state.language == L"zh_CN") body =
        L"Mira 需要 Microsoft Visual C++ x64 Runtime " MIRA_WIDEN(MIRA_VC_RUNTIME_MIN_VERSION) L" 或更高版本。\n\n"
        L"请从 Microsoft 安装此运行库，在 Microsoft 安装窗口中阅读并接受许可，然后重新打开 Mira。"
        L"Mira 不包含此独立的 Microsoft 组件。\n\n是否打开 Microsoft 官方下载页面？";
    else body =
        L"Для Mira нужен Microsoft Visual C++ x64 Runtime " MIRA_WIDEN(MIRA_VC_RUNTIME_MIN_VERSION) L" или новее.\n\n"
        L"Установите его с сайта Microsoft, ознакомьтесь с лицензией в установщике Microsoft и снова откройте Mira. "
        L"Этот отдельный компонент Microsoft не входит в комплект Mira.\n\nОткрыть официальную страницу загрузки Microsoft?";
    if (graphical) {
        if (MessageBoxW(nullptr, body, L"Mira Media Downloader", MB_YESNO | MB_DEFBUTTON2 | MB_ICONINFORMATION) == IDYES)
            ShellExecuteW(nullptr, L"open", MIRA_WIDEN(MIRA_VC_RUNTIME_HELP_URL), nullptr, nullptr, SW_SHOWNORMAL);
    } else {
        int bytes = WideCharToMultiByte(CP_UTF8, 0, body, -1, nullptr, 0, nullptr, nullptr);
        if (bytes > 1) {
            std::string text(static_cast<size_t>(bytes), '\0');
            WideCharToMultiByte(CP_UTF8, 0, body, -1, &text[0], bytes, nullptr, nullptr);
            text.resize(static_cast<size_t>(bytes - 1));
            text += "\n" MIRA_VC_RUNTIME_HELP_URL "\n";
            WriteBytes(STD_ERROR_HANDLE, text);
        }
    }
}
} // namespace

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE, PWSTR, int) {
    SetCurrentProcessExplicitAppUserModelID(kAppUserModelId);
    State state;
    state.language = Preference(L"MIRA_STARTUP_LANGUAGE", L"ui_language", L"ru");
    if (state.language != L"ru" && state.language != L"en" && state.language != L"zh_CN") state.language = L"ru";
    state.dark = Preference(L"MIRA_STARTUP_THEME", L"ui_theme", L"light") == L"dark";
    std::wstring timeout = Environment(L"MIRA_STARTUP_TIMEOUT_MS");
    if (!timeout.empty()) {
        wchar_t* end = nullptr;
        unsigned long value = wcstoul(timeout.c_str(), &end, 10);
        if (end && !*end && value >= 1000 && value <= 120000) state.timeout = value;
    }
    // Optional QA evidence only. Claim a new file; never overwrite an existing
    // path, and never record command lines, environment contents or user data.
    std::wstring trace = Environment(L"MIRA_STARTUP_TRACE");
    if (!trace.empty() && ((trace.size() > 2 && trace[1] == L':' && (trace[2] == L'\\' || trace[2] == L'/')) ||
                           trace.rfind(L"\\\\", 0) == 0))
        state.trace.reset(CreateFileW(trace.c_str(), GENERIC_WRITE, FILE_SHARE_READ, nullptr, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr));
    bool graphical = !IsCommandMode();
    RuntimeRequirement runtime = CheckSystemRuntime();
    if (RuntimeDiagnosticRequested()) {
        WriteRuntimeDiagnostic(runtime);
        return runtime.satisfied ? 0 : ERROR_MOD_NOT_FOUND;
    }
    if (!runtime.satisfied) {
        state.reason = "runtime_missing"; state.exitCode = ERROR_MOD_NOT_FOUND;
        state.exited = state.elapsed(); state.writeTrace();
        ReportRuntimeRequirement(state, graphical);
        return ERROR_MOD_NOT_FOUND;
    }
    state.reason = graphical ? "starting" : "command_mode";
    if (graphical) ShowSplash(instance, state);
    Handle readyEvent;
    std::wstring eventName = graphical ? CreateReadyEvent(readyEvent) : std::wstring();
    if (graphical && eventName.empty()) {
        DWORD error = GetLastError() ? GetLastError() : ERROR_GEN_FAILURE;
        Dismiss(state); state.exitCode = error; state.reason = "event_error"; state.exited = state.elapsed(); state.writeTrace();
        ReportError(state, graphical, false, error); return static_cast<int>(error);
    }
    wchar_t executable[32768]{};
    DWORD pathLength = GetModuleFileNameW(nullptr, executable, static_cast<DWORD>(sizeof(executable) / sizeof(wchar_t)));
    std::wstring path(executable, pathLength);
    size_t separator = path.find_last_of(L"\\/");
    std::wstring core = path.substr(0, separator + 1) + L"runtime\\MiraMediaDownloaderCore.exe";
    std::wstring command = L"\"" + core + L"\"" + RawArgumentTail();
    std::vector<wchar_t> mutableCommand(command.begin(), command.end());
    mutableCommand.push_back(L'\0');
    auto environment = ChildEnvironment(eventName);
    Handle job(CreateJobObjectW(nullptr, nullptr));
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    if (!job.value || !SetInformationJobObject(job.value, JobObjectExtendedLimitInformation, &limits, sizeof(limits))) {
        DWORD error = GetLastError();
        Dismiss(state); state.exitCode = error; state.reason = "job_error"; state.exited = state.elapsed(); state.writeTrace();
        ReportError(state, graphical, false, error); return static_cast<int>(error);
    }
    state.job = job.value;
    PROCESS_INFORMATION process{};
    ChildStartup startup;
    DWORD creation = CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT;
    if (!startup.inherited.empty()) creation |= EXTENDED_STARTUPINFO_PRESENT;
    if (!startup.valid() || !CreateProcessW(core.c_str(), mutableCommand.data(), nullptr, nullptr,
                                           !startup.inherited.empty(), creation, environment.data(), nullptr,
                                           &startup.info.StartupInfo, &process)) {
        DWORD error = GetLastError() ? GetLastError() : ERROR_GEN_FAILURE;
        Dismiss(state); state.exitCode = error; state.reason = "launch_error"; state.exited = state.elapsed(); state.writeTrace();
        ReportError(state, graphical, false, error); return static_cast<int>(error);
    }
    Handle coreProcess(process.hProcess), coreThread(process.hThread);
    state.process = process.hProcess;
    state.processId = process.dwProcessId;
    if (!AssignProcessToJobObject(job.value, process.hProcess)) {
        DWORD error = GetLastError();
        TerminateProcess(process.hProcess, error);
        WaitForSingleObject(process.hProcess, 5000);
        Dismiss(state); state.exitCode = error; state.reason = "job_attach_error"; state.exited = state.elapsed(); state.writeTrace();
        ReportError(state, graphical, false, error); return static_cast<int>(error);
    }
    state.spawned = state.elapsed();
    if (ResumeThread(process.hThread) == static_cast<DWORD>(-1)) {
        DWORD error = GetLastError();
        TerminateJobObject(job.value, error);
        WaitForSingleObject(process.hProcess, 5000);
        Dismiss(state); state.exitCode = error; state.reason = "resume_error"; state.exited = state.elapsed(); state.writeTrace();
        ReportError(state, graphical, false, error); return static_cast<int>(error);
    }
    coreThread.reset();
    state.writeTrace();
    bool ready = !graphical;
    for (;;) {
        HANDLE watched[] = { coreProcess.value, readyEvent.value };
        DWORD count = ready ? 1 : 2;
        DWORD result = MsgWaitForMultipleObjectsEx(count, watched, ready ? INFINITE : 250, QS_ALLINPUT, MWMO_INPUTAVAILABLE);
        if (result == WAIT_OBJECT_0) break;
        if (!ready && result == WAIT_OBJECT_0 + 1) {
            ready = true;
            state.ready = state.elapsed(); state.reason = "ready";
            Dismiss(state); state.writeTrace();
        }
        MSG message{};
        while (PeekMessageW(&message, nullptr, 0, 0, PM_REMOVE)) { TranslateMessage(&message); DispatchMessageW(&message); }
        if (!ready && !state.cancelled && !state.timedOut && state.elapsed() >= state.timeout) {
            state.timedOut = true; state.reason = "timeout";
            TerminateJobObject(job.value, ERROR_TIMEOUT);
            Dismiss(state); state.writeTrace();
            // The exact core handle is the only fallback target if its job
            // cannot stop it. Never match or terminate a process by name.
            if (WaitForSingleObject(coreProcess.value, 5000) != WAIT_OBJECT_0) TerminateProcess(coreProcess.value, ERROR_TIMEOUT);
        }
        if (state.cancelled && WaitForSingleObject(coreProcess.value, 0) != WAIT_OBJECT_0)
            TerminateProcess(coreProcess.value, ERROR_CANCELLED);
    }
    DWORD code = 0;
    GetExitCodeProcess(coreProcess.value, &code);
    if (state.cancelled) code = ERROR_CANCELLED;
    else if (state.timedOut) code = ERROR_TIMEOUT;
    else if (!ready && graphical) state.reason = code == 0 ? "core_exit_before_ready" : "core_error";
    state.exitCode = code; state.exited = state.elapsed();
    Dismiss(state); state.writeTrace();
    if (graphical && (state.timedOut || (!ready && !state.cancelled && code != 0)))
        ReportError(state, true, state.timedOut, code);
    return static_cast<int>(code); // Preserve worker/CLI exit codes exactly.
}
