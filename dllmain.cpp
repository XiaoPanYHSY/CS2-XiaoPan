// ✅ 修复头文件顺序 + 宏定义
#define WIN32_LEAN_AND_MEAN  // 减少 Windows.h 的冗余内容
#define _WIN32_WINNT 0x0600  // 支持 inet_pton（Windows Vista+）
// dllmain.cpp : 定义 DLL 应用程序的入口点。
#include "pch.h"
#include <winsock2.h>
#include <ws2tcpip.h>  // 支持 inet_pton
#include <windows.h>   // 必须放在 winsock2.h 之后
#include <mmsystem.h>
#include <iostream>
#include <tlhelp32.h>
#include <nlohmann/json.hpp>
#include <fstream>
#include <string>
#include <chrono>
#pragma comment(lib, "winmm.lib")
#pragma comment(lib, "ws2_32.lib")  // 链接 Winsock 库


// 添加 DLL 导出定义
extern "C" __declspec(dllexport) void StartESP();

using json = nlohmann::json;
using namespace std;

// UDP客户端类
class UDPClient {
private:
    SOCKET sock;
    sockaddr_in serverAddr;
    bool initialized;

public:
    UDPClient() : sock(INVALID_SOCKET), initialized(false) {
        WSADATA wsaData;
        if (WSAStartup(MAKEWORD(2, 2), &wsaData) != 0) {
            cerr << "WSAStartup failed" << endl;
            return;
        }
        initialized = true;
    }

    ~UDPClient() {
        if (sock != INVALID_SOCKET) {
            closesocket(sock);
        }
        if (initialized) {
            WSACleanup();
        }
    }

    bool Connect(const char* ip, int port) {
        sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
        if (sock == INVALID_SOCKET) {
            cerr << "Socket creation failed" << endl;
            return false;
        }

        // 启用广播功能
        BOOL broadcast = TRUE;
        setsockopt(sock, SOL_SOCKET, SO_BROADCAST,
            (char*)&broadcast, sizeof(broadcast));

        serverAddr.sin_family = AF_INET;
        serverAddr.sin_port = htons(port);

        // 如果是广播地址
        if (strcmp(ip, "255.255.255.255") == 0) {
            serverAddr.sin_addr.s_addr = INADDR_BROADCAST;
        }
        else {
            inet_pton(AF_INET, ip, &serverAddr.sin_addr);
        }

        return true;
    }

    bool Send(const string& data) {
        if (sock == INVALID_SOCKET) return false;

        int bytesSent = sendto(sock, data.c_str(), (int)data.size(), 0,
            (sockaddr*)&serverAddr, sizeof(serverAddr));
        return bytesSent != SOCKET_ERROR;
    }
};

// 全局UDP客户端
UDPClient udpClient;

// 向量结构
struct Vector3 {
    float x, y, z;

    Vector3 operator-(const Vector3& other) const { return { x - other.x, y - other.y, z - other.z }; }

    void Normalize() {
        float length = sqrt(x * x + y * y + z * z);
        if (length != 0) { x /= length; y /= length; z /= length; }
    }

    float Dot(const Vector3& other) const { return x * other.x + y * other.y + z * other.z; }

    void Print(const char* label) const { std::cout << label << ": (" << x << ", " << y << ", " << z << ")\n"; }
};


// 内存读取类
class Memory {
private:
    uintptr_t ProcessID = 0;
    HANDLE HProcessID = nullptr; // 初始化为 nullptr

public:
    Memory(std::string ProcessName) noexcept {
        PROCESSENTRY32 entry = {};
        entry.dwSize = sizeof(PROCESSENTRY32);
        const auto Snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);

        // 遍历进程，找到目标进程
        while (Process32Next(Snapshot, &entry)) {
            if (wcscmp(entry.szExeFile, std::wstring(ProcessName.begin(), ProcessName.end()).c_str()) == 0) {
                ProcessID = entry.th32ProcessID;
                HProcessID = OpenProcess(PROCESS_ALL_ACCESS, 0, ProcessID);
                break;
            }
        }
        CloseHandle(Snapshot);
    }

    // 检查进程是否仍在运行
    bool IsProcessRunning() const noexcept {
        if (HProcessID == nullptr) {
            return false; // 如果句柄为空，进程不在运行
        }

        DWORD exitCode;
        if (GetExitCodeProcess(HProcessID, &exitCode)) {
            if (exitCode == STILL_ACTIVE) {
                return true; // 进程仍在运行
            }
            else {
                // 进程已退出，关闭句柄
                CloseHandle(HProcessID);
                return false; // 进程已退出
            }
        }
        return false; // 如果无法获取退出码，假设进程不在运行
    }

    uintptr_t Get_Module(std::string ModuleName) noexcept {
        MODULEENTRY32 entry = {};
        entry.dwSize = sizeof(MODULEENTRY32);
        const auto Snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, ProcessID);
        uintptr_t dwModuleBaseAddress = 0;

        // 获取模块基址
        while (Module32Next(Snapshot, &entry)) {
            if (wcscmp(entry.szModule, std::wstring(ModuleName.begin(), ModuleName.end()).c_str()) == 0) {
                dwModuleBaseAddress = reinterpret_cast<uintptr_t>(entry.modBaseAddr);
                break;
            }
        }
        CloseHandle(Snapshot);
        return dwModuleBaseAddress;
    }

    std::string ReadString(uintptr_t address, size_t maxLength = 128) noexcept {
        char* buffer = new char[maxLength + 1];  // +1 for null terminator
        memset(buffer, 0, maxLength + 1);

        SIZE_T bytesRead;
        if (ReadProcessMemory(HProcessID, (LPCVOID)address, buffer, maxLength, &bytesRead)) {
            std::string result(buffer);
            delete[] buffer;
            return result;
        }

        delete[] buffer;
        return "unknown";  // 返回默认值
    }

    template <class T>
    T Read(uintptr_t Address) noexcept {
        T Value = {};
        ReadProcessMemory(HProcessID, (LPVOID)(Address), &Value, sizeof(T), 0);
        return Value;
    }


    string Read_str(uintptr_t Address) noexcept//读取内存(字符串)
    {
        char Buffer[MAX_PATH]{};
        ReadProcessMemory(HProcessID, (LPVOID)(Address), &Buffer, MAX_PATH, 0);
        return Buffer;
    }
};

// 偏移管理器
class OffsetManager {
private:
    json offsets;

public:
    OffsetManager(const std::string& filePath) {
        std::ifstream file(filePath);
        if (file.is_open()) {
            file >> offsets;
            file.close();
        }
        else {
            std::cerr << "无法打开偏移文件: " << filePath << std::endl;
        }
    }

    uintptr_t GetOffset(const std::string& key) {
        if (offsets.contains(key)) {
            std::string hexString = offsets[key].get<std::string>(); // 获取十六进制字符串
            return std::stoul(hexString, nullptr, 16); // 16 进制转换
        }
        std::cerr << "偏移键未找到: " << key << std::endl;
        return 0;
    }
};

// **全局偏移变量**（直接定义，不再从文件读取）
namespace CS2_Offsets {
    uintptr_t dwViewAngles = 0x23176C8;
    uintptr_t dwLocalPlayerPawn = 0x2066B60;
    uintptr_t dwEntityList = 0x24AC2A8;
    uintptr_t m_pGameSceneNode = 0x338;
    uintptr_t m_vecOrigin = 0x88;
    uintptr_t m_iHealth = 0x354;
    uintptr_t m_ArmorValue = 0x272C;
    uintptr_t m_hPlayerPawn = 0x90C;
    uintptr_t m_angEyeAngles = 0x3DD0;
    uintptr_t m_iTeamNum = 0x3F3;
    uintptr_t m_lifeState = 0x35C;
    uintptr_t m_modelState = 0x160;
    uintptr_t m_iszPlayerName = 0x6F8;
    uintptr_t m_pClippingWeapon = 0x3DC0;
    uintptr_t m_iItemDefinitionIndex = 0x1582;
    uintptr_t dwViewMatrix = 0x230CFA0;
    uintptr_t m_vOldOrigin = 0x1588;
    uintptr_t m_fFlags = 0x400;
    uintptr_t m_bIsScoped = 0x26F8;
    uintptr_t m_pInGameMoneyServices = 0x808;
    uintptr_t m_iAccount = 0x40;
    uintptr_t dwGameRules = 0x230AF60;
    uintptr_t m_bBombPlanted = 0x8C7;
    uintptr_t m_iIDEntIndex = 0x3EAC;
    uintptr_t dwGameTypes = 0x1B8000;
    uintptr_t dwGameTypes_mapName = 0x120;
    uintptr_t vecLastClipCameraPos = 0x3DA4;

    // 初始化函数（现在只用于设置，不再读取文件）
    void LoadOffsets() {
        // 这里直接使用上面定义的偏移量，不需要从文件读取
        // 只是为了保持接口一致性
    }
}

// **初始化偏移**（简化）
void InitializeOffsets() {
    CS2_Offsets::LoadOffsets();
}


Memory CS2_MEM = { "cs2.exe" };

// 获取实体列表
uintptr_t EntityList(uintptr_t moduleBase) noexcept {
    return CS2_MEM.Read<uintptr_t>(moduleBase + CS2_Offsets::dwEntityList);
}


// 转换玩家
uintptr_t Convert(uintptr_t entityList, uintptr_t player) noexcept {
    return CS2_MEM.Read<uintptr_t>(CS2_MEM.Read<uintptr_t>(entityList + 8 * ((player & 0x7FFF) >> 9) + 16) + 112 * (player & 0x1FF));
}

uintptr_t Traverse_Player(short i, uintptr_t moduleBase, BOOL returnPlayerController = false) noexcept {
    const auto entityList = EntityList(moduleBase); // 调用 EntityList，传入 moduleBase
    const auto playerController = Convert(entityList, i);
    if (returnPlayerController)
        return playerController;
    return Convert(entityList, CS2_MEM.Read<uint32_t>(playerController + CS2_Offsets::m_hPlayerPawn));
}



string Player_Name(short i, uintptr_t moduleBase) noexcept//通过ClassID获取名称
{
    const auto entityList = EntityList(moduleBase); // 调用 EntityList，传入 moduleBase
    const auto PlayerController = Convert(entityList, i);
    if (!PlayerController)return "None";
    else return CS2_MEM.Read_str(PlayerController + CS2_Offsets::m_iszPlayerName);
}

int Money(short i, uintptr_t moduleBase) noexcept {
    const auto entityList = EntityList(moduleBase); // 获取 EntityList
    const auto playerController = Convert(entityList, i); // 获取 PlayerController
    if (!playerController) return 0; // 如果 playerController 无效，返回 0

    // 读取 InGameMoneyServices 指针
    uintptr_t moneyServicesPtr = CS2_MEM.Read<uintptr_t>(playerController + CS2_Offsets::m_pInGameMoneyServices);
    if (!moneyServicesPtr) return 0; // 确保指针有效

    // **读取账户金钱 (4 字节)**
    return CS2_MEM.Read<int>(moneyServicesPtr + CS2_Offsets::m_iAccount);
}

uintptr_t localPlayer = 0;
int localPlayerTeamNumber = 0;

enum BoneIndex {
    BONE_WAIST = 0,
    BONE_NECK = 5,
    BONE_HEAD = 6,
    BONE_SHOULDER_LEFT = 8,
    BONE_FOREARM_LEFT = 9,
    BONE_HAND_LEFT = 11,
    BONE_SHOULDER_RIGHT = 13,
    BONE_FOREARM_RIGHT = 14,
    BONE_HAND_RIGHT = 16,
    BONE_KNEE_LEFT = 23,
    BONE_FEET_LEFT = 24,
    BONE_KNEE_RIGHT = 26,
    BONE_FEET_RIGHT = 27
};

struct BonePosition {
    float x, y, z;
};

std::vector<BonePosition> ReadSpecificBones(uintptr_t bone_matrix, const std::vector<BoneIndex>& bone_indices) {
    std::vector<BonePosition> bones(bone_indices.size());

    for (size_t i = 0; i < bone_indices.size(); ++i) {
        uintptr_t bone_offset = bone_matrix + bone_indices[i] * 0x20;
        bones[i].x = CS2_MEM.Read<float>(bone_offset);
        bones[i].y = CS2_MEM.Read<float>(bone_offset + 0x4);
        bones[i].z = CS2_MEM.Read<float>(bone_offset + 0x8);
    }

    return bones;
}

// 发送JSON数据通过UDP
void SendJsonData(const json& data, const string& dataType) {
    json packet = {
        {"type", dataType},
        {"data", data}
    };
    string jsonStr = packet.dump();
    udpClient.Send(jsonStr);
}

// DLL 启动函数
void StartESP() {
    // 广播到整个局域网
    if (!udpClient.Connect("255.255.255.255", 6564)) {
        cerr << "Failed to connect UDP server" << endl;
        return;
    }

    bool processFound = false;  // 进程找到的标志

    // 等待进程启动
    while (!CS2_MEM.IsProcessRunning()) {
        CS2_MEM = Memory("cs2.exe"); // 重新尝试获取进程
    }

    processFound = true;  // 进程找到，标志置为 true

    while (true) {
        // 检查进程是否仍在运行
        if (!CS2_MEM.IsProcessRunning()) {
            processFound = false; // 更新标志为 false，表示进程退出

            // 等待进程重新启动
            while (!CS2_MEM.IsProcessRunning()) {
                CS2_MEM = Memory("cs2.exe"); // 重新尝试获取进程
                if (CS2_MEM.IsProcessRunning()) {
                    processFound = true; // 更新标志为 true，表示进程找到
                    break; // 退出内部循环
                }
            }
        }

        try {
            auto start = std::chrono::high_resolution_clock::now();
            json esp_data = json::array();
            json playerData;
            json entityData;
            json bones_data = json::array();
            json view_matrix_data; // 创建 JSON 对象

            if (processFound) {
                // 如果找到进程并且正在运行，执行主逻辑
                if (processFound) {

                    int enemyCount = 0; // 计数器，用于跟踪已找到的敌人数量
                    // 获取模块基地址
                    uintptr_t moduleBase = CS2_MEM.Get_Module("client.dll");
                    uintptr_t matchmaking = CS2_MEM.Get_Module("matchmaking.dll");


                    // 计算本地玩家地址
                    uintptr_t localPlayerAddress = moduleBase + CS2_Offsets::dwLocalPlayerPawn;

                    // 读取本地玩家指针
                    uintptr_t localPlayer = CS2_MEM.Read<uintptr_t>(localPlayerAddress);

                    // 计算队伍编号的地址
                    uintptr_t localPlayerTeamNumberAddress = localPlayer + CS2_Offsets::m_iTeamNum;

                    // 读取队伍编号
                    uint32_t localPlayerTeamNumber = CS2_MEM.Read<uint32_t>(localPlayerTeamNumberAddress);

                    uint32_t AimPawm = CS2_MEM.Read<short>(localPlayer + CS2_Offsets::m_iIDEntIndex);

                    // 获取实体列表地址
                    uintptr_t entity_list = CS2_MEM.Read<uintptr_t>(moduleBase + CS2_Offsets::dwEntityList);
                    // 计算实体条目地址
                    uintptr_t ent_entry = CS2_MEM.Read<uintptr_t>(entity_list + 0x8 * (AimPawm >> 9) + 0x10);
                    // 计算最终实体地址
                    uintptr_t entity = CS2_MEM.Read<uintptr_t>(ent_entry + 112 * (AimPawm & 0x1FF));

                    // 视图矩阵的起始地址
                    uintptr_t viewMatrixAddress = moduleBase + CS2_Offsets::dwViewMatrix;

                    // 声明视图矩阵数组
                    float view_matrix[16];


                    // 读取敌人队伍编号
                    uint32_t entityTeamNumber = CS2_MEM.Read<uint32_t>(entity + CS2_Offsets::m_iTeamNum);

                    int aim_check = 0;  // 默认 0
                    int esp = 0;        // 用于存储按下的按键
                    int radar = 0;        // 用于存储按下的按键
                    int recoil = 0;        // 用于存储按下的按键
                    int aim_move = 0;        // 用于存储按下的按键


                    // 读取本地玩家的 GameSceneNode
                    uintptr_t gameSceneNode = CS2_MEM.Read<uintptr_t>(localPlayer + CS2_Offsets::m_pGameSceneNode);
                    Vector3 localPlayerWorldOrigin = CS2_MEM.Read<Vector3>(gameSceneNode + CS2_Offsets::m_vecOrigin);
                    Vector3 localPlayerviewAngles = CS2_MEM.Read<Vector3>(localPlayer + CS2_Offsets::m_angEyeAngles);
                    Vector3 localcamera = CS2_MEM.Read<Vector3>(localPlayer + CS2_Offsets::vecLastClipCameraPos);


                    // 如果AimPawm大于0，表示准星指向了实体，执行开枪
                    if ((GetAsyncKeyState(VK_XBUTTON1) & 0x8000) || (GetAsyncKeyState(VK_XBUTTON2) & 0x8000)) {  // 检测侧键1或侧键2是否按下
                        if (AimPawm > 0 && (entityTeamNumber == 2 || entityTeamNumber == 3) && entityTeamNumber != localPlayerTeamNumber) {
                            aim_check = 1;
                        }
                    }

                    if (GetAsyncKeyState(VK_F1) & 0x8000) {  // 检测 F1 键是否按下
                        esp = 1;
                    }

                    if (GetAsyncKeyState(VK_F2) & 0x8000) {  // 检测 F1 键是否按下
                        esp = 2;
                    }

                    if (GetAsyncKeyState(VK_F3) & 0x8000) {  // 检测 F1 键是否按下
                        radar = 1;
                    }

                    if (GetAsyncKeyState(VK_F4) & 0x8000) {  // 检测 F1 键是否按下
                        radar = 2;
                    }

                    if (GetAsyncKeyState(VK_LBUTTON) & 0x8000) {  // 检查左键是否按下
                        recoil = 1;
                    }

                    if (GetAsyncKeyState(VK_XBUTTON1) & 0x8000) {  // 检测 F1 键是否按下
                        aim_move = 1;        // 用于存储按下的按键
                    }

                    if (GetAsyncKeyState(VK_XBUTTON2) & 0x8000) {  // 检测 F1 键是否按下
                        aim_move = 1;        // 用于存储按下的按键
                    }


                    uintptr_t localgame_scene_node = CS2_MEM.Read<uintptr_t>(localPlayer + CS2_Offsets::m_pGameSceneNode);
                    uintptr_t localbone_matrix = CS2_MEM.Read<uintptr_t>(localgame_scene_node + CS2_Offsets::m_modelState + 0x80);

                    float locallegX = CS2_MEM.Read<float>(localbone_matrix + 28 * 0x20);
                    float locallegY = CS2_MEM.Read<float>(localbone_matrix + 28 * 0x20 + 0x4);
                    float locallegZ = CS2_MEM.Read<float>(localbone_matrix + 28 * 0x20 + 0x8);
                    const auto localClippingWeapon = CS2_MEM.Read<short>(CS2_MEM.Read<uintptr_t>(localPlayer + CS2_Offsets::m_pClippingWeapon) + CS2_Offsets::m_iItemDefinitionIndex);

                    uintptr_t mapNameAddress = CS2_MEM.Read<uintptr_t>(matchmaking + CS2_Offsets::dwGameTypes + CS2_Offsets::dwGameTypes_mapName);
                    std::string mapName = CS2_MEM.ReadString(mapNameAddress + 0x4, 32);

                    playerData["localPlayer"] = {
                        {"worldOrigin", {localPlayerWorldOrigin.x, localPlayerWorldOrigin.y, localPlayerWorldOrigin.z}},
                        {"viewAngles", {localPlayerviewAngles.x, localPlayerviewAngles.y, localPlayerviewAngles.z}},
                        {"localcamera", {localcamera.x, localcamera.y, localcamera.z}},
                        {"team", localPlayerTeamNumber},
                        {"locallegX", locallegX},
                        {"locallegY", locallegY},
                        {"locallegZ", locallegZ},
                        {"localClippingWeapon", localClippingWeapon},
                        {"mapName", mapName},
                    };


                    uint32_t C4PlanTime = CS2_MEM.Read<short>(CS2_MEM.Read<uintptr_t>(moduleBase + CS2_Offsets::dwGameRules) + CS2_Offsets::m_bBombPlanted);
                    esp_data.push_back({
                           { "C4PlanTime", C4PlanTime }
                        });

                    // 模拟逐元素读取
                    for (int i = 0; i < 16; i++) {
                        view_matrix[i] = CS2_MEM.Read<float>(viewMatrixAddress + i * sizeof(float));
                    }

                    // 将视图矩阵存入 JSON 对象
                    view_matrix_data["view_matrix"] = std::vector<float>(view_matrix, view_matrix + 16);


                    for (int i = 0; i < 64; ++i) {

                        const auto PlayerPawn = Traverse_Player(i, moduleBase);
                        const std::string PlayerName = Player_Name(i, moduleBase);
                        const auto moneyServices = Money(i, moduleBase);

                        const auto health = CS2_MEM.Read<int>(PlayerPawn + CS2_Offsets::m_iHealth);
                        const auto ArmorValue = CS2_MEM.Read<int>(PlayerPawn + CS2_Offsets::m_ArmorValue);
                        const auto TeamNumber = CS2_MEM.Read<int>(PlayerPawn + CS2_Offsets::m_iTeamNum);
                        const auto state = CS2_MEM.Read<int>(PlayerPawn + CS2_Offsets::m_fFlags);
                        const auto Scoped = CS2_MEM.Read<int>(PlayerPawn + CS2_Offsets::m_bIsScoped);
                        const auto ClippingWeapon = CS2_MEM.Read<short>(CS2_MEM.Read<uintptr_t>(PlayerPawn + CS2_Offsets::m_pClippingWeapon) + CS2_Offsets::m_iItemDefinitionIndex);


                        if (PlayerPawn != localPlayer && TeamNumber != localPlayerTeamNumber && (TeamNumber == 2 || TeamNumber == 3)) {

                            uintptr_t game_scene_node = CS2_MEM.Read<uintptr_t>(PlayerPawn + CS2_Offsets::m_pGameSceneNode);
                            uintptr_t bone_matrix = CS2_MEM.Read<uintptr_t>(game_scene_node + CS2_Offsets::m_modelState + 0x80);

                            const auto worldPosition = CS2_MEM.Read<Vector3>(game_scene_node + CS2_Offsets::m_vecOrigin);
                            const auto viewAngles = CS2_MEM.Read<Vector3>(PlayerPawn + CS2_Offsets::m_angEyeAngles);
                            float legZ = CS2_MEM.Read<float>(bone_matrix + 28 * 0x20 + 0x8);

                            // 定义需要的骨骼点索引
                            std::vector<BoneIndex> needed_bones = {
                                BONE_WAIST,
                                BONE_NECK,
                                BONE_HEAD,
                                BONE_SHOULDER_LEFT,
                                BONE_FOREARM_LEFT,
                                BONE_HAND_LEFT,
                                BONE_SHOULDER_RIGHT,
                                BONE_FOREARM_RIGHT,
                                BONE_HAND_RIGHT,
                                BONE_KNEE_LEFT,
                                BONE_FEET_LEFT,
                                BONE_KNEE_RIGHT,
                                BONE_FEET_RIGHT
                            };

                            // 批量读取需要的骨骼点
                            auto bones = ReadSpecificBones(bone_matrix, needed_bones);

                            // 解析骨骼点坐标
                            Vector3 waist = { bones[0].x, bones[0].y, bones[0].z };
                            Vector3 neck = { bones[1].x, bones[1].y, bones[1].z };
                            Vector3 head = { bones[2].x, bones[2].y, bones[2].z + 8 }; // 头部 Z 坐标 + 8
                            Vector3 shoulder_left = { bones[3].x, bones[3].y, bones[3].z };
                            Vector3 forearm_left = { bones[4].x, bones[4].y, bones[4].z };
                            Vector3 hand_left = { bones[5].x, bones[5].y, bones[5].z };
                            Vector3 shoulder_right = { bones[6].x, bones[6].y, bones[6].z };
                            Vector3 forearm_right = { bones[7].x, bones[7].y, bones[7].z };
                            Vector3 hand_right = { bones[8].x, bones[8].y, bones[8].z };
                            Vector3 knee_left = { bones[9].x, bones[9].y, bones[9].z };
                            Vector3 feet_left = { bones[10].x, bones[10].y, bones[10].z };
                            Vector3 knee_right = { bones[11].x, bones[11].y, bones[11].z };
                            Vector3 feet_right = { bones[12].x, bones[12].y, bones[12].z };


                            if (health > 0) {

                                bones_data.push_back({
                                       {"entity_index", i},
                                       {"headX", head.x}, {"headY", head.y}, {"headZ", head.z},
                                       {"neckX", neck.x}, {"neckY", neck.y}, {"neckZ", neck.z},
                                       {"waistX", waist.x}, {"waistY", waist.y}, {"waistZ", waist.z},
                                       {"shoulderleftX", shoulder_left.x}, {"shoulderleftY", shoulder_left.y}, {"shoulderleftZ", shoulder_left.z},
                                       {"foreleftX", forearm_left.x}, {"foreleftY", forearm_left.y}, {"foreleftZ", forearm_left.z},
                                       {"handleftX", hand_left.x}, {"handleftY", hand_left.y}, {"handleftZ", hand_left.z},
                                       {"shoulderrightX", shoulder_right.x}, {"shoulderrightY", shoulder_right.y}, {"shoulderrightZ", shoulder_right.z},
                                       {"forerightX", forearm_right.x}, {"forerightY", forearm_right.y}, {"forerightZ", forearm_right.z},
                                       {"handrightX", hand_right.x}, {"handrightY", hand_right.y}, {"handrightZ", hand_right.z},
                                       {"kneeleftX", knee_left.x}, {"kneeleftY", knee_left.y}, {"kneeleftZ", knee_left.z},
                                       {"feetleftX", feet_left.x}, {"feetleftY", feet_left.y}, {"feetleftZ", feet_left.z},
                                       {"kneerightX", knee_right.x}, {"kneerightY", knee_right.y}, {"kneerightZ", knee_right.z},
                                       {"feetrightX", feet_right.x}, {"feetrightY", feet_right.y}, {"feetrightZ", feet_right.z}
                                    });

                                entityData["id"] = i;
                                entityData["PlayerName"] = PlayerName;
                                entityData["health"] = health;
                                entityData["team"] = TeamNumber;
                                entityData["worldPosition"] = { worldPosition.x, worldPosition.y, worldPosition.z };
                                entityData["viewAngles"] = { viewAngles.x, viewAngles.y, viewAngles.z };
                                entityData["localcamera"] = { localcamera.x, localcamera.y, viewAngles.z };
                                playerData["entities"].push_back(entityData);

                                esp_data.push_back({
                                     {"entity_index", i},
                                     {"PlayerName", PlayerName},
                                     {"legZ", legZ},
                                     {"health", health},
                                     {"ArmorValue", ArmorValue},
                                     {"ClippingWeapon", ClippingWeapon},
                                     {"moneyServices", moneyServices},
                                     {"state", state},
                                     {"Scoped", Scoped }
                                    });

                            }
                            enemyCount++; // 增加计数器
                            // 检查找到的敌人数
                            if (enemyCount == 5) {
                                break;
                            }
                        }
                    }
                    // 创建 JSON 数据
                    json outputData;
                    outputData["aim_check"] = aim_check;
                    outputData["esp"] = esp;
                    outputData["radar"] = radar;
                    outputData["recoil"] = recoil;
                    outputData["aim_move"] = aim_move;

                    // 通过UDP发送数据
                    SendJsonData(view_matrix_data, "view_matrix");
                    SendJsonData(esp_data, "esp_data");
                    SendJsonData(playerData, "player_data");
                    SendJsonData(bones_data, "bones_data");
                    SendJsonData(outputData, "output");
                }
            }
        }
        catch (const std::exception& e) {
            std::cerr << "发生异常: " << e.what() << "\n";
        }
    }
}

// DLL 的入口点
BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpvReserved) {
    switch (fdwReason) {
    case DLL_PROCESS_ATTACH:
        InitializeOffsets(); // 加载偏移
        StartESP();
        break;
    case DLL_THREAD_ATTACH:
    case DLL_THREAD_DETACH:
    case DLL_PROCESS_DETACH:
        break;
    }
    return TRUE;
}