<template>
  <div class="auth-layout">
    <aside class="auth-visual">
      <img src="/teaser.png" alt="芯明鉴登录视觉图" class="auth-visual__image" />
      <div class="auth-visual__overlay">
        <div class="auth-visual__content">
          <span class="auth-visual__logo">
            <img src="/favicon.png" alt="芯明鉴" />
          </span>
          <h1>芯明鉴</h1>
          <p>基于 YOLOv11 的 PCB 缺陷智能检测平台</p>
        </div>
      </div>
    </aside>

    <main class="auth-panel">
      <div class="auth-panel__inner">
        <slot />
      </div>
    </main>
  </div>
</template>

<style lang="scss" scoped>
.auth-layout {
  display: flex;
  width: 100%;
  height: 100vh;
  overflow: hidden;
}

.auth-visual {
  position: relative;
  flex: 1;
  height: 100vh;
  min-width: 0;
  overflow: hidden;
  background: #eef6fd;

  &__image {
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: center;
    opacity: 0.72;
  }

  &__overlay {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: flex-end;
    padding: 48px;
    background: rgba(238, 246, 253, 0.2);
  }

  &__content {
    max-width: 420px;
    padding: 24px;
    border: 1px solid rgba(191, 216, 244, 0.82);
    border-radius: 20px;
    background: rgba(255, 255, 255, 0.9);
    color: $text-primary;

    h1 {
      font-size: 28px;
      font-weight: 600;
      line-height: 1.3;
      margin-bottom: 12px;
    }

    p {
      font-size: 15px;
      line-height: 1.6;
      color: $text-secondary;
    }
  }

  &__logo {
    display: inline-grid;
    place-items: center;
    width: 52px;
    height: 52px;
    overflow: hidden;
    margin-bottom: 20px;
    border: 1px solid $border-color;
    border-radius: 14px;
    background: #fff;

    img {
      width: 50px;
      height: 50px;
      max-width: none;
      object-fit: contain;
      transform: translate(-3.5%, -3%) scale(1.2);
    }
  }
}

.auth-panel {
  flex: 0 0 clamp(520px, 46vw, 680px);
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px clamp(32px, 4vw, 56px);
  overflow-y: auto;
  background:
    radial-gradient(circle at 80% 0%, rgba(91, 124, 250, 0.08), transparent 40%),
    linear-gradient(180deg, #f8fbff 0%, #f5f7fc 100%),
    $bg-color;

  &__inner {
    width: 100%;
    max-width: 460px;
  }
}

@media (max-width: 960px) {
  .auth-layout {
    flex-direction: column;
    height: 100vh;
    overflow: hidden;
  }

  .auth-visual {
    flex: none;
    width: 100%;
    height: clamp(200px, 32vh, 280px);
    min-height: 0;

    &__overlay {
      padding: 20px 24px;
    }

    &__content {
      h1 {
        font-size: 22px;
      }

      p {
        font-size: 13px;
      }
    }

    &__logo {
      margin-bottom: 12px;
    }
  }

  .auth-panel {
    flex: 1;
    width: 100%;
    height: auto;
    min-height: 0;
    padding: 24px 24px 32px;
  }
}
</style>
