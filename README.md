# Local Compute

여러 대의 Windows PC로 파일 작업을 나눠 처리하는 앱입니다.

비개발자도 쓰기 쉽게 화면을 메뉴별로 나눴습니다.

## 설치

아래 설치 파일을 실행합니다.

```text
dist\LocalComputeMCP-Setup.exe
```

설치 후 바탕화면 또는 시작 메뉴에서 `Local Compute`를 엽니다.

## 앱 메뉴

| 메뉴 | 하는 일 |
|---|---|
| 기기 등록 | 작업을 도와줄 다른 PC를 연결합니다. |
| 공유폴더 관리 | A컴퓨터에 공용 폴더를 만들고 input/outputs/logs를 관리합니다. |
| 파일 처리 | 처리할 파일 폴더를 고르고 시작합니다. |
| 실행중인 로그 | 앱이 지금 무엇을 하는지 보여줍니다. |
| 에러 로그 | 실패한 파일과 이유만 따로 보여줍니다. |
| MCP 연결방법 | Codex/Cursor 같은 도구와 연결할 때만 봅니다. |

## 가장 쉬운 사용 순서

1. A컴퓨터와 B컴퓨터에 앱을 설치합니다.
2. B컴퓨터에서 `기기 등록` 메뉴를 엽니다.
3. B컴퓨터에서 `기기 연결 허용`을 누릅니다.
4. B컴퓨터 화면에 6자리 번호가 뜹니다.
5. A컴퓨터에서 `기기 등록` 메뉴를 엽니다.
6. A컴퓨터에서 `번호로 기기 추가`를 누르고 번호를 입력합니다.
7. A컴퓨터에서 `공유폴더 관리` 메뉴를 엽니다.
8. `이 PC를 공유폴더 PC로 설정`을 누릅니다.
9. `파일 처리` 메뉴에서 파일 폴더를 고릅니다.
10. `파일 처리 시작`을 누릅니다.

## 공유폴더 구조

A컴퓨터 기준으로 아래 폴더를 만듭니다.

```text
C:\LocalComputeShare
  input
  outputs
  logs
```

사용자는 `input` 폴더에 처리할 파일을 넣고, 결과는 `outputs` 폴더에서 확인합니다.

## 어떤 작업을 실행할 수 있나요?

기본 화면에서는 복잡한 명령어를 숨겼습니다.

고급 설정을 켜면 아래 같은 작업도 실행할 수 있습니다.

```text
python check_excel.py {input_q} {output_dir_q}
powershell -ExecutionPolicy Bypass -File check.ps1 {input_q}
node check.js {input_q} {output_dir_q}
mytool.exe {input_q} {output_dir_q}
```

주의: B/C 컴퓨터에서도 같은 프로그램이 설치되어 있어야 합니다. 예를 들어 Python 작업이면 B/C에도 Python과 필요한 패키지가 있어야 합니다.

## 아직 알아야 할 점

`기기 연결 허용`과 `번호로 기기 추가`는 PC 주소를 쉽게 등록하기 위한 기능입니다. 실제 원격 작업 실행은 현재 SSH 방식도 함께 사용합니다. 따라서 원격 PC에서 작업을 돌리려면 Windows OpenSSH 또는 이후 Worker Mode가 필요합니다.

현재 앱은 “비개발자용 메뉴 구조”로 정리 중이며, 다음 단계는 SSH 없이 앱끼리 바로 작업을 주고받는 Worker Mode입니다.
