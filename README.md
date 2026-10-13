# Google Drive WebDAV Mount

Google Drive("내 드라이브" 및 "공유 문서함")를 Windows 로컬 드라이브(`G:`)로 마운트합니다.

## 1. 사전 준비 (Credentials)

Google Cloud Console에서 다운로드한 OAuth 클라이언트 자격 증명(`client_secrets.json`)을 아래 경로에 저장합니다:
- `%USERPROFILE%\.config\google-drive\client_secrets.json`

## 2. 사용 방법

| 작업 | 명령 | 설명 |
| :--- | :--- | :--- |
| **설치** | `install.bat` | 도구 설치 (`uv tool`) |
| **상태 체크** | `status.bat` | API 연결 및 마운트 상태 확인 |
| **마운트** | `mount.bat` | `G:` 드라이브로 마운트 |
| **마운트 해제** | `umount.bat` | `G:` 드라이브 마운트 해제 |

---

### 참고: Windows WebDAV 전송 제한 해제
Windows 기본 파일 전송 제한(~50MB)을 4GB로 확장하고 HTTP 마운트를 허용하려면, 관리자 권한으로 1회 실행합니다:
- `scripts\fix-FileSizelimitInBytes-and-restart-WebClient.bat`
