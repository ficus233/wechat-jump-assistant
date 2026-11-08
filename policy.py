"""User-selectable experimental policy; warnings are separate from execution."""
import math
from core import validate_model_signature

def landing_result(error_px,continue_on_deviation=True):
    """A large/unknown landing error is recorded without declaring success."""
    if error_px is not None and math.isfinite(error_px) and error_px<=25:return '成功'
    if continue_on_deviation:return '偏差继续'
    raise ValueError('落点偏差较大或未知，需人工判断')

def plan_press(model,signature,distance,*,free=False,trial_ms=None,max_ms=1500,
               input_verified=True,confidence=1.,automatic=False):
    warnings=[]
    if trial_ms is not None:ms=float(trial_ms)
    else:
        if not model:raise ValueError('没有模型时，请填写试跳ms并点击“一次试跳”')
        try:validate_model_signature(model,signature)
        except ValueError as e:
            if not free:raise
            warnings.append(str(e))
        if not input_verified:
            if not free:raise ValueError('先完成一次试跳并确认游戏响应')
            warnings.append('输入响应尚未确认')
        if not model['min_d']<=distance<=model['max_d']:
            if not free:raise ValueError('目标超出校准距离范围，先试跳扩充样本')
            warnings.append('超出采样范围，使用模型外推')
        if automatic and confidence<.8:
            if not free:raise ValueError('自动模式目标置信度不足，暂停')
            warnings.append('采用低置信度目标')
        ms=model['k']*distance+model['b']
    if not math.isfinite(ms) or ms<=0:raise ValueError('时长必须是有限正数')
    if not 30<=ms<=max_ms:
        if not free:raise ValueError('预测时长越界')
        warnings.append('时长超出默认范围，按指定值执行')
    return ms,warnings
