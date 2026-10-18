// Native Mac display capture and GamePad codec worker. Barista codec: GPL-2.0.
// stdin: I (IDR) or P (predicted); stdout: GPF1, IDR byte, 5 LE sizes/chunks.
#import <Foundation/Foundation.h>
#import <ScreenCaptureKit/ScreenCaptureKit.h>
#import <CoreGraphics/CoreGraphics.h>
#import <CoreMedia/CoreMedia.h>
#import <CoreVideo/CoreVideo.h>
#include "drh/encoder/x264/encoder.h"
#include <mutex>
#include <thread>
#include <atomic>
#include <iostream>
#include <unistd.h>
using namespace barista::drh;
static std::mutex pixelMutex;
static std::vector<uint8_t> latest(DrcVideoFrameBytes,128);
static std::atomic<bool> gotPixels{false};
static SCStream *activeStream;
static id activeOutput;
static void EncodeWorker();
static void Write32(uint32_t value) { for (int i=0;i<4;++i) putchar(value>>(i*8)); }
@interface CaptureOutput : NSObject <SCStreamOutput,SCStreamDelegate>
@end
@implementation CaptureOutput
- (void)stream:(SCStream*)stream didStopWithError:(NSError*)error
{
 if(stream!=activeStream)return;
 fprintf(stderr,"Display capture stopped, error code %ld\n",(long)error.code);
 exit(4);
}
- (void)stream:(SCStream*)stream didOutputSampleBuffer:(CMSampleBufferRef)sample ofType:(SCStreamOutputType)type
{
 if(type!=SCStreamOutputTypeScreen || !CMSampleBufferIsValid(sample))return;
 CVPixelBufferRef pb=CMSampleBufferGetImageBuffer(sample);
 static bool reported=false;
 if(pb && !reported){fprintf(stderr,"Capture pixel format %08x, size %zux%zu\n",CVPixelBufferGetPixelFormatType(pb),CVPixelBufferGetWidth(pb),CVPixelBufferGetHeight(pb));reported=true;}
 if(!pb || CVPixelBufferGetWidth(pb)!=DrcVideoWidth || CVPixelBufferGetHeight(pb)!=DrcVideoHeight)return;
 CVPixelBufferLockBaseAddress(pb,kCVPixelBufferLock_ReadOnly);
 std::vector<uint8_t> image(DrcVideoFrameBytes,128);
 if(CVPixelBufferGetPixelFormatType(pb)==kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange && CVPixelBufferGetPlaneCount(pb)==2)
 {
  auto y=(const uint8_t*)CVPixelBufferGetBaseAddressOfPlane(pb,0);
  auto uv=(const uint8_t*)CVPixelBufferGetBaseAddressOfPlane(pb,1);
  size_t ys=CVPixelBufferGetBytesPerRowOfPlane(pb,0),cs=CVPixelBufferGetBytesPerRowOfPlane(pb,1);
  for(size_t row=0;row<DrcVideoHeight;++row)memcpy(image.data()+row*DrcVideoWidth,y+row*ys,DrcVideoWidth);
  size_t u=DrcVideoWidth*DrcVideoHeight,v=u+u/4;
  for(size_t row=0;row<DrcVideoHeight/2;++row)for(size_t x=0;x<DrcVideoWidth/2;++x)
  {image[u+row*DrcVideoWidth/2+x]=uv[row*cs+x*2];image[v+row*DrcVideoWidth/2+x]=uv[row*cs+x*2+1];}
 }
 else { CVPixelBufferUnlockBaseAddress(pb,kCVPixelBufferLock_ReadOnly);return; }
 CVPixelBufferUnlockBaseAddress(pb,kCVPixelBufferLock_ReadOnly);
 { std::lock_guard lock(pixelMutex);latest.swap(image); }
 if(!gotPixels.exchange(true))fprintf(stderr,"Live display pixels received\n");
}
@end
static void EncodeWorker()
{
 auto encoder=x264::CreateEncoder({});
 if(!encoder || !encoder->IsValid())exit(3);
 int request;bool initialized=false;
 while((request=getchar())!=EOF)
 {
  if(request!='I' && request!='P')continue;
  while(!gotPixels.load())usleep(10000);
  std::vector<uint8_t> pixels;
  { std::lock_guard lock(pixelMutex);pixels=latest; }
  std::string error;
  auto frame=encoder->Encode(pixels,request=='I'||!initialized,error);
  if(!frame){fprintf(stderr,"Encoder rejected frame\n");exit(5);}
  if(getenv("GAMEPAD_CODEC_REFERENCE")){fwrite("RAW1",1,4,stdout);Write32(pixels.size());fwrite(pixels.data(),1,pixels.size(),stdout);}
  fwrite("GPF1",1,4,stdout);putchar(frame->idr?1:0);
  for(const auto& chunk:frame->chunks){Write32(chunk.bytes.size());fwrite(chunk.bytes.data(),1,chunk.bytes.size(),stdout);}
  fflush(stdout);initialized=true;
 }
 exit(0);
}
int main(int argc,char**argv){ @autoreleasepool {
 setvbuf(stdout,nullptr,_IOFBF,65536);
 [SCShareableContent getShareableContentExcludingDesktopWindows:NO onScreenWindowsOnly:YES completionHandler:^(SCShareableContent* content,NSError* error){
  if(error || !content.displays.count){fprintf(stderr,"Display permission/content unavailable, error code %ld\n",(long)error.code);exit(2);}
  SCDisplay *display=content.displays.firstObject;
  for(SCDisplay* d in content.displays)if(d.displayID==CGMainDisplayID())display=d;
  SCContentFilter *filter=[[SCContentFilter alloc]initWithDisplay:display excludingWindows:@[]];
  SCStreamConfiguration *cfg=[SCStreamConfiguration new];cfg.width=DrcVideoWidth;cfg.height=DrcVideoHeight;
  cfg.pixelFormat=kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange;cfg.minimumFrameInterval=CMTimeMake(1,60);cfg.queueDepth=3;cfg.showsCursor=YES;
  cfg.capturesAudio=NO;
  CaptureOutput* output=[CaptureOutput new];
  activeOutput=output;
  activeStream=[[SCStream alloc]initWithFilter:filter configuration:cfg delegate:output];
  NSError* addError=nil;
  if(![activeStream addStreamOutput:output type:SCStreamOutputTypeScreen sampleHandlerQueue:dispatch_queue_create("gamepad.display",DISPATCH_QUEUE_SERIAL) error:&addError]){fprintf(stderr,"Cannot attach display output\n");exit(2);}
  [activeStream startCaptureWithCompletionHandler:^(NSError* startError){
   if(startError){fprintf(stderr,"Display capture start failed, error code %ld\n",(long)startError.code);exit(2);}
   fprintf(stderr,"Display capture started at 864x480\n");
   std::thread(EncodeWorker).detach();
  }];
 }];
 [[NSRunLoop currentRunLoop]run];
 }return 0;}
