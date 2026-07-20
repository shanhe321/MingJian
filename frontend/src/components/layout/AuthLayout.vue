<template>
  <div class="auth-layout">
    <aside class="auth-visual">
      <img src="/teaser.png" alt="PCB 缺陷检测平台" class="auth-visual__image" />
      <div class="auth-visual__overlay">
        <div class="auth-visual__content">
          <img src="/favicon.svg" alt="logo" class="auth-visual__logo" />
          <h1>PCB Defect Detection Platform</h1>
          <p>基于 YOLOv11 的目标检测智能体平台</p>
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
  min-height: 100vh;
}

.auth-visual {
  position: relative;
  flex: 1;
  min-height: 100vh;
  overflow: hidden;
  background: #0f2e36;

  &__image {
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: center;
  }

  &__overlay {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: flex-end;
    padding: 48px;
    background: linear-gradient(
      180deg,
      rgba(15, 46, 54, 0.08) 0%,
      rgba(15, 46, 54, 0.55) 55%,
      rgba(15, 46, 54, 0.82) 100%
    );
  }

  &__content {
    max-width: 420px;
    color: #fff;

    h1 {
      font-size: 28px;
      font-weight: 600;
      line-height: 1.3;
      margin-bottom: 12px;
    }

    p {
      font-size: 15px;
      line-height: 1.6;
      color: rgba(255, 255, 255, 0.82);
    }
  }

  &__logo {
    width: 44px;
    height: 44px;
    margin-bottom: 20px;
  }
}

.auth-panel {
  flex: 0 0 480px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px 40px;
  background:
    radial-gradient(circle at 80% 0%, rgba(91, 124, 250, 0.08), transparent 40%),
    linear-gradient(180deg, #f8fbff 0%, #f5f7fc 100%),
    $bg-color;

  &__inner {
    width: 100%;
    max-width: 380px;
  }
}

@media (max-width: 960px) {
  .auth-layout {
    flex-direction: column;
  }

  .auth-visual {
    flex: none;
    min-height: 240px;
    max-height: 320px;

    &__overlay {
      padding: 24px 32px;
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
      width: 36px;
      height: 36px;
      margin-bottom: 12px;
    }
  }

  .auth-panel {
    flex: 1;
    padding: 32px 24px 48px;
  }
}
</style>
