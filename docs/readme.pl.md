<div align="center">

# 🖥️ DeskMate

**Jedno okno zawsze na wierzchu dla tych wszystkich drobiazgów, które kopiujesz i uruchamiasz cały dzień.**

Lista tekstów z 15 przyciskami kopiowania · karteczki · launcher aplikacji · lupa ekranowa ·
uruchamiacz skryptów · wybierak znaków — wszystko w jednym przenośnym `.exe`.

[![Wersja](https://img.shields.io/badge/version-v2.7-89b4fa?style=flat-square)](../.dev/version_info.txt)
[![Platforma](https://img.shields.io/badge/platforma-Windows%2010%20%7C%2011-0078d4?style=flat-square&logo=windows&logoColor=white)](#-wymagania)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776ab?style=flat-square&logo=python&logoColor=white)](#-wymagania)
[![GUI](https://img.shields.io/badge/GUI-PyQt6%20%C2%B7%20Qt%206-41cd52?style=flat-square&logo=qt&logoColor=white)](#-wymagania)
[![Licencja](https://img.shields.io/badge/licencja-Freeware-a6e3a1?style=flat-square)](#-licencja)
[![Testy](https://img.shields.io/badge/testy-pytest-f38ba8?style=flat-square)](#-testy)

[**English**](../README.md) · [Lupa — szczegóły techniczne](Magnifier.md) · [Zgłoś błąd](https://github.com/polsoft-it)

</div>

---

## 📖 Opis

**DeskMate** (wcześniej *Desktop Mate*) to mały towarzysz pulpitu dla Windowsa. Główne okno trzyma
**15 pól tekstowych**, każde z własnym przyciskiem kopiowania, a pasek u góry uruchamia narzędzia
potrzebne w danej chwili — bez wychodzenia z aplikacji, w której właśnie pracujesz.

Wszystko działa w **jednym procesie**: narzędzia pomocnicze są zapakowane w plik wykonywalny
i startują z górnego paska, więc nie ma nic dodatkowego do instalowania, żadnej ikony w zasobniku
ani usługi w tle. Interfejs jest dostępny w **angielskim i polskim**, z motywem
**ciemnym (Catppuccin Mocha)** i **jasnym (w stylu Visual Studio)**.

> **Cel projektu:** odpowiedzieć na pytanie *„co muszę mieć teraz pod ręką?”* jednym kliknięciem —
> i nigdy nie zabierać fokusu aplikacji, w której pracujesz.

---

## ✨ Funkcje

### 📝 Główne okno — lista tekstów

- **15 niezależnych pól tekstowych**, każde z przyciskiem **Kopiuj** (z potwierdzeniem „Skopiowano!”).
- **Wklej całość ➜ podziel na listę** — wklej blok tekstu (linie, wartości rozdzielone `;`/`,`,
  listy numerowane, punkty), a inteligentny podział rozłoży go na 15 pól.
- **Kopiuj wszystko**, **Wyczyść wszystko** oraz **Eksport / Import `.txt`** dla całej listy tabel.
- **Autozapis** — lista jest zapisywana po każdej zmianie (z opóźnieniem), więc nic nie ginie przy zamykaniu.
- **Zawsze na wierzchu** (`📌`) oraz **tryb kompaktowy** (`🗕`), który zwija okno do małej ikony;
  podwójne kliknięcie ikony przywraca okno.
- **Pasek stanu na żywo** — `n/15 wypełnionych`, potwierdzenia zapisu/eksportu/importu i komunikaty błędów.
- **Pozycja i rozmiar okna, stan „na wierzchu”, język, motyw i skróty są pamiętane.**

### 🖥️ Górny pasek — dziewięć narzędzi w jednym rzędzie

| Przycisk | Narzędzie | Do czego służy |
| :---: | --- | --- |
| <img src="../Desktop.png" width="18" height="18" alt=""> | **Desktop Launcher** | Dodaje aplikacje, skróty, foldery i skrypty do listy lub siatki ikon; prawy przycisk: *Dodaj / Dodaj folder / Otwórz / Właściwości / Usuń*. Pokazuje natywną ikonę Windows pliku. |
| 🔍 | **Lupa** | Podążająca za kursorem lupa zawsze na wierzchu (1,5×–20×). Globalne skróty, filtry, zamrożenie obrazu. |
| `>_` | **psLauncher (mod)** | Wybierz plik `.ps1/.bat/.cmd/.vbs/.js/.wsf/.hta/.py` i uruchom go, opcjonalnie **jako administrator** (UAC). Okno z podglądem wyników na żywo. |
| ™ | **Character Picker** | Siatka 5×5 znaków specjalnych (`™ © ® § ✓ ∞ ♪ …`); kliknięcie kopiuje znak. Edytowalna siatka + skrót do Windows Character Map. |
| 🗕 | **Kompakt** | Zwija okno do pływającej ikony; podwójne kliknięcie przywraca. |
| 📌 | **Na wierzchu** | Przypina okno nad innymi aplikacjami. |
| ⚙ | **Ustawienia** | Język, motyw, lokalizacja zapisu notatek, wspólny plik tabel i skróty globalne. |
| ℹ | **O programie** | Autor, wersja, linki i lista aplikacji w programie. |
| 🗑 📋 💾 📂 📝 | **Akcje listy** | Wyczyść, Kopiuj wszystko, Eksportuj, Importuj, Notatki. |

### 🔍 Lupa — `magnifier.py`

Bezramkowa lupa zawsze na wierzchu, która podąża za kursorem na **wszystkich monitorach**, sterowana
globalnym hookiem myszy, więc nigdy nie potrzebuje fokusu.

- Adaptacyjne renderowanie: `LANCZOS` poniżej 4×, ostry `NEAREST` + kontrast krawędzi (krzywa S) powyżej 4×.
- Bez migotania (jeden trwały element canvas), oszczędna przy bezczynności (brak przechwytywania,
  gdy kursor stoi), przechwytywanie ograniczone do ~45 fps.
- `Alt` + kółko = zoom (kroki 1,25×), podwójne kliknięcie lub `Esc` zamyka, `Ctrl+Alt+L` pokaż/ukryj,
  `Ctrl+Alt+F` zamroź obraz, `Ctrl+Alt+I` odwróć kolory, `Ctrl+Alt+C` podbij kontrast.
- 📘 Pełny opis techniczny: **[Magnifier.md](Magnifier.md)**

### 📝 Notatki — `sticky_notes.py`

- Wiele swobodnie ustawianych karteczek, **przeciąganych** za pasek tytułu.
- **8 gotowych kolorów** + własny wybór koloru, **przypięcie „na wierzchu”** dla każdej notatki osobno.
- **Edytowalny tytuł**, autozapis na żywo (400 ms) do JSON, usuwanie notatki z potwierdzeniem.
- Notatki podążają za językiem programu (PL/EN); lokalizację pliku danych ustawisz w **Ustawieniach**.

### ⌨️ Skróty globalne — `hotkeys.py`

- Dwa konfigurowalne skróty: **pokaż/ukryj główne okno** oraz **pokaż/ukryj notatki**.
- Każdy może być **kombinacją klawiszy** (rejestrowaną systemowo przez `RegisterHotKey`, więc działa,
  gdy fokus ma inna aplikacja) albo **gestem myszy** (kliknięcie / podwójne kliknięcie z modyfikatorami).
- Konflikty są wykrywane i zgłaszane; skróty, których system odmówi, są komunikowane i nadal działają,
  gdy program ma fokus.

---

## 🚀 Szybki start

### ▶️ Uruchomienie ze źródeł

```powershell
# 1) pobierz kod
git clone https://github.com/polsoft-it/DeskMate.git
cd DeskMate

# 2) zainstaluj jedyną zewnętrzną zależność
pip install PyQt6

# 3) uruchom program (bez okna konsoli)
pythonw DesktopMate.pyw
```

> Lupa dodatkowo wymaga **Pillow** (`pip install pillow`) — w `.exe` jest zapakowana,
> ale uruchamiana ze źródeł potrzebuje tej paczki.

### 📦 Wersja przenośna (`.exe`)

```powershell
.dev\build.bat
```

Skrypt aktualizuje PyInstallera, czyści `.dev\build` i `.dev\dist` i buduje **jednoplikowy,
okienkowy** plik wykonywalny z ikoną i metadanymi wersji:

```
.dev\dist\DesktopMate.exe
```

### 🧩 Jak startują narzędzia w `.exe`

Narzędzia **nie są** osobnymi programami. W wersji skompilowanej kliknięcie przycisku na górnym
pasku uruchamia ponownie ten sam plik `.exe` z odpowiednim przełącznikiem, a proces potomny uruchamia
zapakowany skrypt zamiast głównego okna:

| Przełącznik | Skrypt |
| --- | --- |
| `--run-magnifier` | `magnifier.py` |
| `--run-pslauncher` | `pslauncher.py` |
| `--run-character-picker` | `character_picker.py` |

Ten sam przełącznik działa z terminala (`DesktopMate.exe --run-pslauncher`), a ponowne kliknięcie
przycisku zamyka narzędzie razem z całym drzewem procesów.

---

## ⚙️ Wymagania

| Element | Wartość |
| --- | --- |
| **System** | Windows 10 / 11 (API Win32 przez `ctypes`, `tkinter`, `os.startfile`) |
| **Python** | 3.10+ (rozwijane i testowane na 3.14) |
| **GUI** | [PyQt6](https://pypi.org/project/PyQt6/) — główne okno, launcher, notatki, wybierak |
| **Lupa** | [Pillow](https://pypi.org/project/pillow/) + `tkinter` (w instalatorze python.org) |
| **psLauncher** | tylko `tkinter`; interpretery, które uruchamia, muszą być w `PATH` |
| **Budowanie (opcjonalnie)** | PyInstaller (instaluje go `.dev\build.bat`) |

> Jeśli `import tkinter` nie działa, uruchom ponownie instalator Pythona i włącz komponent
> **tcl/tk and IDLE**. `tkinter` nie da się zainstalować przez `pip`.

---

## 📁 Struktura projektu

```
DeskMate/
├── DesktopMate.pyw          # punkt wejścia: główne okno, motyw, język, ustawienia, dispatch narzędzi
├── desktop_launcher.py      # okno „Desktop”: lista/siatka aplikacji, wpisy, właściwości
├── sticky_notes.py          # karteczki: widget notatki + menedżer + magazyn JSON
├── hotkeys.py               # globalne skróty klawiszowe/myszy (RegisterHotKey, hooki WH_*)
├── magnifier.py             # lupa ekranowa (tkinter + Pillow + hooki Win32)
├── pslauncher.py            # uruchamiacz skryptów: rozszerzenia, elevacja, okno wyników
├── sandbox.py               # opcjonalny moduł sandbox/output używany przez psLauncher
├── character_picker.py      # wybierak znaków specjalnych 5×5
├── Desktop.png              # ikona Desktop Launchera
├── pslauncher_icon.png      # ikona psLaunchera
├── zasoby i dane            # text_list_data.json, sticky_notes_data.json, desktop_launcher_data.json
├── tests                   # testy pytest (launcher, notatki, pslauncher, lupa)
├── docs/
│   ├── readme.pl.md         # ten README po polsku
│   └── Magnifier.md         # lupa: potok renderowania, hooki, wnętrze
└── .dev/
    ├── DesktopMate.spec     # spec PyInstallera (narzędzia, pliki danych, ukryte importy)
    ├── build.bat            # budowanie wersji przenośnej jednym poleceniem
    ├── version_info.txt     # metadane wersji EXE (v2.7)
    └── icon.ico             # ikona aplikacji
```

---

## 🗂️ Pliki danych

DeskMate trzyma swój stan w zwykłych, czytelnych plikach JSON obok pliku wykonywalnego
(lub obok `DesktopMate.pyw` wersji źródłowej). Usunięcie pliku resetuje odpowiednią część programu.

| Plik | Zawartość |
| --- | --- |
| `text_list_data.json` | 15 pól, tekst zbiorczy, język, motyw, „na wierzchu”, ścieżka notatek, wspólny plik tabel, skróty, geometria okna |
| `sticky_notes_data.json` | Wszystkie notatki: id, tytuł, treść, kolor, pozycja, rozmiar, przypięcie |
| `desktop_launcher_data.json` | Wpisy launchera: ścieżka, nazwa, własna ikona, flaga folderu |
| `character_settings.json` | 25 znaków wybieraka (zapisywane przy zapisie) |

> Magazyn notatek i wspólny plik tabel można wskazać w dowolnym folderze w **Ustawieniach**;
> notatki przenoszą się wtedy automatycznie za wybranym plikiem.

---

## 💾 Budowanie i pakowanie

`.dev\DesktopMate.spec` jest jedynym źródłem prawdy dla buildu:

- **Zapakowane narzędzia** — `magnifier.py`, `pslauncher.py`, `sandbox.py`, `character_picker.py`.
  Uruchamiane są przez `runpy`, więc PyInstaller nie widzi ich importów: spec **skanuje AST**
  każdego narzędzia i dodaje jego importy (w tym całe drzewa podmodułów `tkinter` / `PIL`)
  jako ukryte importy.
- **Zapakowane dane** — ikony, domyślne JSON-y oraz `icon.ico` (ikona okna jest ładowana w runtime;
  `EXE(icon=...)` oznacza tylko sam plik wykonywalny).
- **Wyjście jednoplikowe, okienkowe** (`console=False`, `upx=True`) z ikoną i metadanymi wersji
  z `.dev\version_info.txt`.

Wersję podnosisz w **dwóch** miejscach: `ABOUT_INFO["version"]` w `DesktopMate.pyw` oraz
`filevers`/`prodvers` i wartości tekstowe w `.dev\version_info.txt`.

---

## 🧪 Testy

Testy działają bez ekranu (`QT_QPA_PLATFORM=offscreen`) i nigdy nie dotykają prawdziwych plików danych.

```powershell
pip install pytest
python -m pytest
```

| Moduł testów | Zakres |
| --- | --- |
| `tests/test_desktop_launcher.py` | lokalizacja pliku wpisów, normalizacja i walidacja JSON, uruchamianie, formatowanie rozmiaru |
| `tests/test_sticky_notes.py` | menedżer notatek, zapis, zmiana ścieżki, język |
| `tests/test_pslauncher.py` | mapowanie rozszerzenie → interpreter, flagi shell/admin, cytowanie |
| `tests/test_magnifier.py` | kroki i zakres zoomu, granice kadru na wirtualnym pulpicie |

---

## 🎨 Motywy

Oba motywy to zwykłe słowniki w `DesktopMate.pyw`, nakładane jednym generowanym arkuszem stylów.

| Motyw | Wygląd |
| --- | --- |
| **Ciemny** (domyślny) | [Catppuccin Mocha](https://github.com/catppuccin/catppuccin) — tło `#1e1e2e`, akcent `#89b4fa` |
| **Jasny** | w stylu Visual Studio — tło `#f3f3f3`, akcent `#0078d4` |

Ikony górnego paska są **rysowane przez `QPainter`** i od razu przemalowywane przy zmianie motywu,
więc pozostają ostre przy każdym DPI.

---

## 🌍 Języki

Wszystkie teksty widoczne dla użytkownika są w jednym słowniku `STRINGS` (`en` / `pl`) w `DesktopMate.pyw`;
notatki i launcher mają własne małe tabele tekstów. Zmiana języka jest natychmiastowa
i zapamiętywana — bez restartu.

---

## ⚠️ Uwagi i ograniczenia

- **Tylko Windows.** Lupa, globalne skróty i uruchamianie plików korzystają z API Win32.
- **Elevacja** (`psLauncher`) idzie przez monit UAC `Start-Process -Verb RunAs`; odmowa jest
  zgłaszana, a nie po cichu ignorowana.
- **Wybierak znaków** zapisuje ustawienia w katalogu roboczym (`character_settings.json`);
  uruchamiaj go z folderu, w którym można pisać.
- **Wpisy launchera** wskazują ścieżki bezwzględne — przeniesienie celu psuje wpis (jest wtedy
  pomijany, bez wysypywania programu).
- **Brak podpisu cyfrowego** — SmartScreen może ostrzegać o niepodpisanym pliku `.exe`.

---

## 🤝 Współpraca

1. Zrób fork repozytorium i utwórz gałąź funkcji.
2. Zachowaj styl projektu: jeden moduł na narzędzie, teksty w tabelach, docstringi wyjaśniające
   *dlaczego*, a nie *co*.
3. Przed pull requestem uruchom `python -m pytest`.
4. Opisz zmianę, a przy pracy nad UI dołącz zrzut ekranu.

Błędy i pomysły na funkcje zgłaszaj w [issue trackerze](https://github.com/polsoft-it).

---

## 📄 Licencja

**Freeware** © Sebastian Januchowski · polsoft.ITS™ Group — darmowe użytkowanie, także komercyjne.
Bez gwarancji; używasz na własną odpowiedzialność.

---

<div align="center">

**DeskMate v2.7** · dla ludzi, którzy codziennie kopiują te same dwanaście rzeczy.

[⬆ Do góry](#-deskmate) · [English](../README.md)

</div>
