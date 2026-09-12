/* Two real FAT16 volumes for exercising the loader's migration without an SD. */
#include <stddef.h>
#include "ff.h"
#include "ff_utf8.h"
#include "diskio.h"

void *memcpy(void*d,const void*s,__SIZE_TYPE__ n){BYTE*a=d;const BYTE*b=s;while(n--)*a++=*b++;return d;}
void *memset(void*d,int v,__SIZE_TYPE__ n){BYTE*a=d;while(n--)*a++=(BYTE)v;return d;}
int memcmp(const void*a,const void*b,__SIZE_TYPE__ n){const BYTE*x=a,*y=b;while(n--){if(*x!=*y)return *x-*y;x++;y++;}return 0;}
int strcmp(const char*a,const char*b){while(*a&&*a==*b){a++;b++;}return (BYTE)*a-(BYTE)*b;}
__SIZE_TYPE__ strlen(const char*s){__SIZE_TYPE__ n=0;while(s[n])n++;return n;}
char *strrchr(const char*s,int c){const char*out=0;do{if(*s==c)out=s;}while(*s++);return (char*)out;}

static void emit(char*out,__SIZE_TYPE__ cap,__SIZE_TYPE__*n,char c){if(*n+1<cap)out[*n]=c;(*n)++;}
static int snprintf(char*out,__SIZE_TYPE__ cap,const char*format,...){
 __builtin_va_list args;__builtin_va_start(args,format);__SIZE_TYPE__ n=0;
 while(*format){
  if(*format!='%'){emit(out,cap,&n,*format++);continue;}format++;
  unsigned width=0;char pad=' ';if(*format=='0'){pad='0';format++;}
  while(*format>='0'&&*format<='9')width=width*10+(*format++-'0');
  if(*format=='s'){const char*s=__builtin_va_arg(args,const char*);while(*s)emit(out,cap,&n,*s++);}
  else if(*format=='c')emit(out,cap,&n,(char)__builtin_va_arg(args,int));
  else{unsigned value=__builtin_va_arg(args,unsigned),count=0;char digits[16];
   do{digits[count++]='0'+value%10;value/=10;}while(value);
   while(width>count){emit(out,cap,&n,pad);width--;}
   while(count)emit(out,cap,&n,digits[--count]);}
  format++;
 }
 if(cap)out[n<cap?n:cap-1]=0;__builtin_va_end(args);return (int)n;
}

static BYTE disks[2][8192*512];
static FATFS volumes[2];
static const char *drives[2]={"sd:","usb:"};
static unsigned diskWrites[2],stats[7],faultMode,faultAt;
static char failedRenameSource[512];
DSTATUS disk_initialize(BYTE drive){return drive>1?STA_NODISK:0;}
DSTATUS disk_status(BYTE drive){return disk_initialize(drive);}
DRESULT disk_read(BYTE drive,BYTE*out,DWORD sector,UINT count){
 if(drive>1||sector>=8192||count>8192-sector)return RES_PARERR;
 memcpy(out,disks[drive]+sector*512,count*512);return RES_OK;
}
DRESULT disk_write(BYTE drive,const BYTE*in,DWORD sector,UINT count){
 if(drive>1||sector>=8192||count>8192-sector)return RES_PARERR;
 memcpy(disks[drive]+sector*512,in,count*512);diskWrites[drive]++;return RES_OK;
}
DRESULT disk_ioctl(BYTE drive,BYTE cmd,void*out){
 if(drive>1)return RES_PARERR;
 if(cmd==CTRL_SYNC)return RES_OK;
 if(cmd==GET_SECTOR_SIZE){*(WORD*)out=512;return RES_OK;}
 if(cmd==GET_SECTOR_COUNT){*(DWORD*)out=8192;return RES_OK;}
 if(cmd==GET_BLOCK_SIZE){*(DWORD*)out=1;return RES_OK;}
 return RES_PARERR;
}
DWORD get_fattime(void){return (46u<<25)|(9u<<21)|(12u<<16);}
static void word(BYTE*d,unsigned offset,WORD value){d[offset]=value;d[offset+1]=value>>8;}
#define API __declspec(dllexport)
API int reboot(void){
 for(unsigned i=0;i<2;i++){int r=f_mount_char(0,drives[i],0);if(r)return r;
  memset(&volumes[i],0,sizeof(FATFS));if((r=f_mount_char(&volumes[i],drives[i],1)))return r;}
 return 0;
}
API int reset(void){
 for(unsigned i=0;i<2;i++){
  f_mount_char(0,drives[i],0);BYTE*d=disks[i];memset(d,0,sizeof(disks[i]));
  d[0]=0xeb;d[1]=0x3c;d[2]=0x90;memcpy(d+3,"MSDOS5.0",8);
  word(d,11,512);d[13]=1;word(d,14,1);d[16]=1;word(d,17,512);word(d,19,8192);
  d[21]=0xf8;word(d,22,32);word(d,24,32);word(d,26,64);d[38]=0x29;
  memcpy(d+54,"FAT16   ",8);word(d,510,0xaa55);word(d,512,0xfff8);word(d,514,0xffff);
 }
 faultMode=faultAt=0;failedRenameSource[0]=0;return reboot();
}
API int mkdirs(const char*path){
 char copy[512];unsigned n=0;do{copy[n]=path[n];}while(path[n++]&&n<sizeof(copy));
 for(unsigned i=0;copy[i];i++)if(copy[i]=='/'&&i>4){char c=copy[i];copy[i]=0;
  int r=f_mkdir_char(copy);copy[i]=c;if(r&&r!=FR_EXIST)return r;}
 int r=f_mkdir_char(copy);return r==FR_EXIST?0:r;
}
API int put(const char*path,const BYTE*data,unsigned size,unsigned hidden){
 char parent[512];unsigned n=0;do{parent[n]=path[n];}while(path[n++]&&n<sizeof(parent));
 char*slash=strrchr(parent,'/');if(slash&&slash-parent>4){*slash=0;int r=mkdirs(parent);if(r)return -100-r;}
 FIL file;UINT written=0;int r=f_open_char(&file,path,FA_WRITE|FA_CREATE_ALWAYS);if(r)return -200-r;
 r=f_write(&file,data,size,&written);int close=f_close(&file);if(r||close||written!=size)return -300-r-close;
 if(hidden){unsigned volume=path[0]=='u';unsigned offset=(unsigned)(file.dir_ptr-volumes[volume].win);
  disks[volume][file.dir_sect*512+offset+11]|=AM_HID;return reboot();}
 return 0;
}
API int get(const char*path,BYTE*out,unsigned capacity){
 FIL file;UINT count=0;int r=f_open_char(&file,path,FA_READ);if(r)return -r;
 if(f_size(&file)>capacity){f_close(&file);return -1000;}
 r=f_read(&file,out,capacity,&count);int close=f_close(&file);return r||close?-100-r-close:(int)count;
}
API int attributes(const char*path){FILINFO info;int r=f_stat_char(path,&info);return r?-r:info.fattrib;}
API int entries(const char*path,char*out,unsigned capacity){
 DIR dir;FILINFO info;int r=f_opendir_char(&dir,path);if(r)return -r;unsigned count=0;
 while(!(r=f_readdir(&dir,&info))&&info.fname[0]){
  const char*s=wchar_to_char(info.fname);while(*s){if(count+2>=capacity){f_closedir(&dir);return -1000;}out[count++]=*s++;}
  out[count++]='\n';
 }
 out[count]=0;int close=f_closedir(&dir);return r||close?-100-r-close:(int)count;
}
API void fail(unsigned mode,unsigned at){faultMode=mode;faultAt=at;}
API void failRenamePath(const char*path){snprintf(failedRenameSource,sizeof(failedRenameSource),"%s",path);}
API unsigned stat(unsigned which){return which==4?diskWrites[0]+diskWrites[1]:stats[which];}
API unsigned writes(unsigned volume){return diskWrites[volume];}
static FRESULT migration_rename(const char*a,const char*b){
 stats[1]++;if((faultMode==1&&stats[1]==faultAt)||
  (failedRenameSource[0]&&!strcmp(a,failedRenameSource)))return FR_DISK_ERR;
 return f_rename_char(a,b);
}
static FRESULT migration_close(FIL*f){
 FRESULT r=f_close(f);stats[3]++;return faultMode==2&&stats[3]==faultAt?FR_DISK_ERR:r;
}
static FRESULT migration_closedir(DIR*d){
 FRESULT r=f_closedir(d);stats[2]++;return faultMode==3&&stats[2]==faultAt?FR_DISK_ERR:r;
}
static FRESULT migration_opendir(DIR*d,const char*p){stats[0]++;return f_opendir_char(d,p);}
static FRESULT migration_stat(const char*p,FILINFO*i){stats[5]++;return f_stat_char(p,i);}
static FRESULT migration_mkdir(const char*p){stats[6]++;return f_mkdir_char(p);}
